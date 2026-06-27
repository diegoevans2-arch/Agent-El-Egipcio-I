"""
agente.py
Orquestador principal del Agente LLM - El Egypcio.
Integra PyQt5 (UI) + MonitorVentana + GestorBitacora en un solo proceso.

Flujo de inicio:
    0. Gate de QA: correr la suite de tests. Si falla, log + popup con bypass
    1. Migrar config.json al formato multi-proveedor si es necesario
    2. Mostrar popup de login (selección proveedor + API key)
    3. Si conecta correctamente → abrir ventana principal
    4. Si cancela → salir

Detener:
    Botón "Cerrar agente" del system tray, o Ctrl+C en terminal.
"""

import sys
import platform
import traceback
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
from PyQt5.QtGui import QIcon

from utils import cargar_config
from monitor import MonitorVentana
from captura import capturar_y_analizar
from bitacora import GestorBitacora, regenerar_frontmatter
from ventana import VentanaAgente, Senales
from gantt import verificar_alertas
from popup_login import PopupLogin, migrar_config_si_necesario

# URL de soporte/consultas (GitHub). Es para CONSULTA, no garantiza solución:
# el QA no puede saber si el usuario modificó el código localmente.
URL_SOPORTE = "https://github.com/diegoevans2-arch/Agent-El-Egipcio-I"

# Nombre del archivo de log de diagnóstico que se escribe si el QA falla.
NOMBRE_LOG_QA = "qa_error_log.txt"


def verificar_ruta_base(config: dict) -> bool:
    """Verifica que la ruta base del proyecto exista."""
    ruta = Path(config.get("ruta_base", ""))
    if not ruta.exists():
        print(f"[ERROR] La ruta base no existe: {ruta}")
        return False
    return True


def guardar_estado(titulo: str):
    import json
    ruta = Path(__file__).parent / "estado.json"
    estado = {
        "ventana_actual": titulo,
        "ultimo_update": datetime.now().isoformat()
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


# ===========================================================================
# Gate de QA pre-arranque
# ===========================================================================
# Antes de iniciar, se corre la suite de QA completa. Si todo pasa, el
# arranque continúa en silencio. Si algo falla, se escribe un log de
# diagnóstico y se muestra un popup con la opción de cerrar o continuar
# bajo el propio riesgo del usuario (bypass).

def _escribir_log_qa(resultado: dict) -> Path:
    """
    Escribe un archivo de diagnóstico con el detalle de los fallos del QA.
    Se guarda en la carpeta del agente (no en el vault), porque el error
    podría ser justamente que el vault no se resuelve.

    Retorna la ruta del log escrito (o None si no se pudo escribir).
    """
    try:
        ruta_log = Path(__file__).parent / NOMBRE_LOG_QA
        lineas = [
            "=" * 70,
            "  EL EGYPCIO — LOG DE DIAGNÓSTICO DEL QA DE ARRANQUE",
            "=" * 70,
            f"Fecha:      {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Python:     {platform.python_version()}",
            f"Sistema:    {platform.system()} {platform.release()}",
            "",
            f"Total de tests:  {resultado.get('total', 0)}",
            f"Exitosos:        {resultado.get('exitosos', 0)}",
            f"Fallos:          {resultado.get('fallos', 0)}",
            f"Errores:         {resultado.get('errores', 0)}",
            f"Gate concluyente: {resultado.get('gate_concluyente', True)}",
            "",
            "Módulos con problemas:",
        ]
        for m in resultado.get("modulos_con_problemas", []):
            lineas.append(f"  - {m}")
        lineas += [
            "",
            "-" * 70,
            "DETALLE TÉCNICO (tracebacks)",
            "-" * 70,
            resultado.get("detalle", "(sin detalle)"),
            "",
            "-" * 70,
            "NOTA",
            "-" * 70,
            "Si modificaste el código del agente, revisa tus cambios primero.",
            "Si crees que es un problema del agente y no de una modificación",
            "local, puedes consultar (no es soporte de solución) en:",
            f"  {URL_SOPORTE}",
            "",
        ]
        ruta_log.write_text("\n".join(lineas), encoding="utf-8")
        return ruta_log
    except Exception as e:
        print(f"[QA] No se pudo escribir el log de diagnóstico: {e}")
        return None


def _mostrar_popup_qa_fallido(resultado: dict, ruta_log) -> bool:
    """
    Muestra un popup crítico indicando que el QA falló, con dos opciones:
    cerrar el agente o continuar bajo el propio riesgo (bypass).

    Retorna:
        True  → el usuario eligió continuar de todas formas
        False → el usuario eligió cerrar el agente
    """
    n_problemas = resultado.get("fallos", 0) + resultado.get("errores", 0)
    modulos = resultado.get("modulos_con_problemas", [])
    modulos_txt = "\n".join(f"  • {m}" for m in modulos) if modulos else "  • (desconocido)"

    ruta_log_txt = str(ruta_log) if ruta_log else "(no se pudo escribir el log)"

    no_concluyente = ""
    if not resultado.get("gate_concluyente", True):
        no_concluyente = (
            "\n⚠ La verificación no pudo completarse del todo (puede faltar "
            "algún módulo o haber un error en el entorno).\n"
        )

    mensaje = (
        f"La verificación de arranque encontró {n_problemas} problema(s) "
        f"en los siguientes módulos:\n\n"
        f"{modulos_txt}\n"
        f"{no_concluyente}\n"
        f"Se generó un archivo de diagnóstico con el detalle técnico en:\n"
        f"{ruta_log_txt}\n\n"
        f"────────────────────────────────────\n"
        f"Si modificaste el código, revisa tus cambios primero.\n"
        f"Si crees que es un problema del agente, puedes consultar en:\n"
        f"{URL_SOPORTE}\n"
        f"(Este canal es para consulta — no garantiza solución, ya que el "
        f"QA no puede saber si hubo modificaciones locales.)\n\n"
        f"Puedes cerrar el agente para revisar, o continuar de todas formas "
        f"bajo tu propio riesgo."
    )

    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("⚠️ Verificación de arranque falló")
    box.setText("El agente detectó posibles problemas antes de iniciar.")
    box.setInformativeText(mensaje)

    # Botones personalizados: el seguro (cerrar) como default
    btn_cerrar = box.addButton("Cerrar agente", QMessageBox.RejectRole)
    btn_continuar = box.addButton("Continuar de todas formas", QMessageBox.AcceptRole)
    box.setDefaultButton(btn_cerrar)

    box.exec_()
    return box.clickedButton() == btn_continuar


def ejecutar_gate_qa() -> bool:
    """
    Corre el QA de arranque y gestiona el resultado.

    Retorna:
        True  → se puede continuar el arranque (QA OK, o el usuario hizo bypass)
        False → se debe abortar el arranque (el usuario eligió cerrar)

    El gate está envuelto en try/except: si el QA mismo explota (no que un
    test falle, sino un error inesperado del runner), no dejamos al usuario
    sin poder arrancar — se trata como no concluyente y se ofrece bypass.
    """
    try:
        from tests.run_qa import correr_qa_para_arranque
        resultado = correr_qa_para_arranque()
    except Exception as e:
        # El gate mismo no pudo correr. No bloqueamos al usuario: logueamos
        # lo que se pueda y ofrecemos bypass.
        print(f"[QA] El gate de QA no pudo ejecutarse: {e}")
        resultado = {
            "ok": False,
            "total": 0, "exitosos": 0, "fallos": 0, "errores": 1,
            "modulos_con_problemas": ["Runner de QA (no pudo iniciar)"],
            "detalle": f"EXCEPCIÓN AL INICIAR EL GATE:\n{traceback.format_exc()}",
            "gate_concluyente": False,
        }

    if resultado.get("ok"):
        # Caso normal: todo pasó. Silencioso — solo un print a consola.
        print(f"[QA] ✅ Verificación de arranque OK "
              f"({resultado.get('total', 0)} tests).")
        return True

    # Hubo problemas: escribir log + mostrar popup con bypass
    print(f"[QA] ❌ Verificación de arranque falló "
          f"({resultado.get('fallos', 0)} fallos, "
          f"{resultado.get('errores', 0)} errores).")
    ruta_log = _escribir_log_qa(resultado)
    continuar = _mostrar_popup_qa_fallido(resultado, ruta_log)
    if continuar:
        print("[QA] ⚠ El usuario eligió continuar pese a los problemas (bypass).")
    else:
        print("[QA] El usuario eligió cerrar el agente.")
    return continuar


def main():
    print("=" * 50)
    print("  Agente LLM - El Egypcio")
    print(f"  Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # Migrar config al nuevo formato si es necesario
    migrar_config_si_necesario()

    # Iniciar PyQt5 ANTES del popup
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Icono global de la aplicación → afecta barra de tareas Windows.
    # Carga defensiva: si el archivo no existe, no rompe el arranque.
    ruta_icono_app = Path(__file__).parent / "assets" / "agente.ico"
    if ruta_icono_app.exists():
        app.setWindowIcon(QIcon(str(ruta_icono_app)))
    else:
        print(f"[Iconos] ⚠ No se encontró {ruta_icono_app} — usando default Windows.")

    # --- Paso 0: Gate de QA pre-arranque ---
    # Corre la suite de QA completa. Si pasa, continúa en silencio. Si falla,
    # escribe un log de diagnóstico y muestra un popup con opción de bypass.
    # Requiere que QApplication ya exista (para los QMessageBox).
    if not ejecutar_gate_qa():
        sys.exit(1)

    # --- Paso 1: Popup de login ---
    popup = PopupLogin()
    if popup.exec_() != QDialog.Accepted:
        print("[Agente] Login cancelado por el usuario. Saliendo.")
        sys.exit(0)
    # Después del exec_ Accepted, el cliente IA ya está en el singleton global

    # --- Paso 2: Verificar ruta base ---
    config = cargar_config()
    if not verificar_ruta_base(config):
        sys.exit(1)

    # --- Paso 3: Iniciar gestor de bitácora ---
    gestor = GestorBitacora()
    senales = Senales()

    # Regenerar frontmatter del .md actual si existe (refleja cualquier cambio
    # en personas_conocidas u otras configs hechas desde el último cierre)
    try:
        regenerar_frontmatter(gestor.ruta)
    except Exception as e:
        print(f"[Agente] No se pudo regenerar frontmatter al iniciar: {e}")

    # --- Paso 4: Iniciar ventana principal ---
    ventana = VentanaAgente(
        senales=senales,
        gestor_bitacora=gestor,
        capturar_fn=capturar_y_analizar
    )
    ventana.show()

    # Callback del monitor — corre en hilo separado
    def on_cambio_ventana(titulo: str, es_reunion: bool):
        if ventana.es_pausado():
            print(f"[Agente] Pausado — ignorando cambio: {titulo[:40]}")
            return

        print(f"\n[Agente] Cambio detectado: {titulo[:60]}")
        try:
            analisis = capturar_y_analizar(titulo, es_reunion)
            gestor.abrir_entrada(analisis)
            guardar_estado(titulo)
            senales.nueva_entrada.emit(analisis)
        except Exception as e:
            print(f"[Agente] Error procesando cambio: {e}")
            senales.actualizar_ui.emit("🔴 Error")

    # Iniciar monitor en hilo separado
    monitor = MonitorVentana(callback_cambio=on_cambio_ventana)
    monitor.iniciar()

    senales.actualizar_ui.emit("🟢 Activo")
    print("[Agente] Interfaz iniciada. Minimiza a la barra de tareas cuando quieras.\n")

    # Verificar alertas de inactividad y mostrarlas en el chat
    alertas = verificar_alertas()
    if alertas:
        mensaje = "**⚠️ Alertas de inactividad al iniciar:**\n\n" + "\n".join(alertas)
        senales.alerta_gantt.emit(mensaje)

    # Loop principal
    try:
        codigo_salida = app.exec_()
    except KeyboardInterrupt:
        print("\n[Agente] Interrupción por teclado...")
        codigo_salida = 0

    # Cierre limpio
    print("\n[Agente] Cerrando...")
    monitor.detener()
    gestor.cerrar_jornada()
    print(f"[Agente] Bitácora guardada: {gestor.ruta}")

    sys.exit(codigo_salida)


if __name__ == "__main__":
    main()
