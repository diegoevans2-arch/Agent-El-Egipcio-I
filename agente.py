"""
agente.py
Orquestador principal del Agente LLM - El Egypcio.
Integra PyQt5 (UI) + MonitorVentana + GestorBitacora en un solo proceso.

Flujo de inicio:
    1. Migrar config.json al formato multi-proveedor si es necesario
    2. Mostrar popup de login (selección proveedor + API key)
    3. Si conecta correctamente → abrir ventana principal
    4. Si cancela → salir

Detener:
    Botón "Cerrar agente" del system tray, o Ctrl+C en terminal.
"""

import sys
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QIcon

from utils import cargar_config
from monitor import MonitorVentana
from captura import capturar_y_analizar
from bitacora import GestorBitacora, regenerar_frontmatter
from ventana import VentanaAgente, Senales
from gantt import verificar_alertas
from popup_login import PopupLogin, migrar_config_si_necesario


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
