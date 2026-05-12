"""
monitor.py
Detecta cambios en la ventana activa del sistema usando un sistema híbrido:
- Apps de escritorio: comparación exacta por nombre de proceso (.exe)
- Browsers y apps UWP: comparación por keywords en el título de ventana
Solo dispara cuando el título se mantiene estable N segundos.
Compatible con Windows usando win32gui + win32process + psutil.
"""

import time
import json
import threading
from pathlib import Path
from datetime import datetime

try:
    import win32gui
    import win32process
except ImportError:
    raise ImportError("Instala pywin32: pip install pywin32")

try:
    import psutil
except ImportError:
    raise ImportError("Instala psutil: pip install psutil")

try:
    import mss
except ImportError:
    raise ImportError("Instala mss: pip install mss")


# ---------------------------------------------------------------------------
# Constantes internas — hosts cuya identidad real está en el título, no el .exe
# ---------------------------------------------------------------------------
# Browsers: una sola ventana puede contener trabajo o entretenimiento.
BROWSERS = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
}

# UWP Hosts: aplicaciones modernas de Windows (Outlook nuevo, Teams nuevo,
# Calendar, Calculadora, etc.) corren bajo este proceso genérico. El título
# de la ventana sí refleja la app real.
UWP_HOSTS = {
    "ApplicationFrameHost.exe",
}


def cargar_config():
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def es_host_por_titulo(nombre_proceso: str) -> bool:
    """
    Retorna True si el proceso debe filtrarse por título (browsers / UWP)
    en lugar de por nombre de ejecutable.
    """
    if not nombre_proceso:
        return False
    proc_lower = nombre_proceso.lower()
    hosts_lower = {h.lower() for h in BROWSERS | UWP_HOSTS}
    return proc_lower in hosts_lower


def es_ventana_relevante(titulo: str, nombre_proceso: str, config: dict) -> bool:
    """
    Determina si una ventana debe ser registrada usando lógica híbrida.

    Flujo:
    1. ¿El proceso está en lista_negra_procesos? -> IGNORAR
    2. ¿El proceso es browser o UWP host?
       SÍ: revisar título contra keywords bloqueadas y laborales
       NO: comparar proceso contra lista_blanca_procesos
    """
    titulo_lower = (titulo or "").lower()
    proceso_lower = (nombre_proceso or "").lower()

    # 1. Lista negra de procesos — siempre ignorar
    lista_negra = [p.lower() for p in config.get("lista_negra_procesos", [])]
    if proceso_lower in lista_negra:
        return False

    # 2. ¿Es un host que se filtra por título? (browser o UWP)
    if es_host_por_titulo(nombre_proceso):
        # 2a. Bloquear si el título contiene alguna keyword negativa
        for kw in config.get("keywords_bloqueadas_browser", []):
            if kw.lower() in titulo_lower:
                return False
        # 2b. Aceptar si el título contiene alguna keyword laboral
        for kw in config.get("palabras_clave_laborales_browser", []):
            if kw.lower() in titulo_lower:
                return True
        # Browser/UWP sin contenido laboral identificable
        return False

    # 3. App de escritorio — comparación exacta por nombre de proceso
    lista_blanca = [p.lower() for p in config.get("lista_blanca_procesos", [])]
    return proceso_lower in lista_blanca


def es_reunion(titulo: str, config: dict) -> bool:
    """Detecta si la ventana activa corresponde a una reunión o llamada."""
    titulo_lower = (titulo or "").lower()
    for kw in config.get("palabras_clave_reunion", []):
        if kw.lower() in titulo_lower:
            return True
    return False


class MonitorVentana:
    """
    Monitorea la ventana activa y notifica cambios estables.
    Un cambio es 'estable' cuando el mismo título se mantiene
    durante `estabilidad_segundos` sin interrupciones.
    """

    def __init__(self, callback_cambio, intervalo_poll=1):
        self.config = cargar_config()
        self.estabilidad = self.config["captura"]["estabilidad_segundos"]
        self.intervalo_poll = intervalo_poll
        self.callback_cambio = callback_cambio

        self._titulo_actual = ""
        self._titulo_candidato = ""
        self._tiempo_candidato = None
        self._corriendo = False
        self._hilo = None

    def _obtener_ventana_activa(self) -> tuple:
        """
        Retorna (titulo, nombre_proceso, rect) de la ventana activa.
        rect es (left, top, right, bottom) o None si falla.
        Devuelve ("", "", None) si no hay ventana o si falla la consulta.
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "", "", None

            titulo = win32gui.GetWindowText(hwnd) or ""
            titulo = titulo.strip()

            # Obtener coordenadas de la ventana
            try:
                rect = win32gui.GetWindowRect(hwnd)  # (left, top, right, bottom)
            except Exception:
                rect = None

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return titulo, "", rect

            try:
                proceso = psutil.Process(pid)
                nombre_proceso = proceso.name() or ""
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                nombre_proceso = ""

            return titulo, nombre_proceso, rect
        except Exception:
            return "", "", None

    def _ventana_en_monitor_seleccionado(self, rect, config) -> bool:
        """
        Verifica si el centro de la ventana está en el monitor seleccionado.
        
        - monitor_captura = -1: todos → siempre True
        - monitor_captura = 1, 2...: monitor específico → verificar por centro
        - Si no hay rect o falla mss → True (no bloquear por error)
        """
        monitor_cfg = config.get("monitor_captura", 1)

        # -1 = capturar todos, no filtrar
        if monitor_cfg == -1:
            return True

        # Sin coordenadas de ventana → no bloquear
        if rect is None:
            return True

        try:
            left, top, right, bottom = rect
            # Centro de la ventana
            cx = (left + right) // 2
            cy = (top + bottom) // 2

            with mss.mss() as sct:
                # Validar que el índice exista
                if monitor_cfg < 1 or monitor_cfg >= len(sct.monitors):
                    return True  # Índice inválido → no bloquear

                mon = sct.monitors[monitor_cfg]
                # Verificar si el centro cae dentro del monitor seleccionado
                en_x = mon["left"] <= cx < (mon["left"] + mon["width"])
                en_y = mon["top"] <= cy < (mon["top"] + mon["height"])
                return en_x and en_y

        except Exception as e:
            print(f"[Monitor] Error verificando monitor: {e}")
            return True  # En caso de error, no bloquear

    def _loop(self):
        """Loop principal de monitoreo."""
        while self._corriendo:
            titulo, nombre_proceso, rect = self._obtener_ventana_activa()

            # Recargar config en cada ciclo para aplicar cambios en caliente
            self.config = cargar_config()

            if titulo == self._titulo_candidato:
                # El mismo título sigue activo — verificar estabilidad
                if self._tiempo_candidato is not None:
                    segundos_estable = (datetime.now() - self._tiempo_candidato).total_seconds()
                    if segundos_estable >= self.estabilidad:
                        if titulo != self._titulo_actual and titulo:
                            if es_ventana_relevante(titulo, nombre_proceso, self.config):
                                # Verificar que la ventana está en el monitor seleccionado
                                if self._ventana_en_monitor_seleccionado(rect, self.config):
                                    es_meet = es_reunion(titulo, self.config)
                                    self._titulo_actual = titulo
                                    self.callback_cambio(titulo, es_meet)
                                else:
                                    # Ventana relevante pero en otro monitor — ignorar captura
                                    self._titulo_actual = titulo
                            else:
                                # Ventana no relevante — actualizar sin disparar
                                self._titulo_actual = titulo
                        self._tiempo_candidato = None  # Reset para evitar disparos repetidos
            else:
                # Nuevo candidato detectado — reiniciar temporizador
                self._titulo_candidato = titulo
                self._tiempo_candidato = datetime.now()

            time.sleep(self.intervalo_poll)

    def iniciar(self):
        """Inicia el monitoreo en un hilo separado."""
        self._corriendo = True
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()
        print(f"[Monitor] Iniciado — estabilidad: {self.estabilidad}s")

    def detener(self):
        """Detiene el monitoreo limpiamente."""
        self._corriendo = False
        if self._hilo:
            self._hilo.join(timeout=3)
        print("[Monitor] Detenido")
