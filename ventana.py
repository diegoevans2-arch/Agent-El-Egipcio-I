"""
ventana.py
Interfaz gráfica PyQt5 del Agente LLM - El Egypcio.
Fase 3: agrega sección de chat expandible con contexto de bitácoras.
"""

import os
import json
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit,
    QSystemTrayIcon, QMenu, QAction, QDialog,
    QDialogButtonBox, QFrame, QSizePolicy, QScrollArea,
    QComboBox, QMessageBox, QSpinBox, QDoubleSpinBox, QCompleter
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QStringListModel
from PyQt5.QtGui import QIcon, QFont, QColor, QPixmap, QCursor

from utils import cargar_config, ruta_bitacoras, ruta_proyectos, uri_obsidian
from chat import GestorChat, SYSTEM_PROMPT
from gantt import (
    agregar_proyecto, editar_proyecto, obtener_proyectos, generar_mermaid,
    PROMPT_CLASIFICACION_DEFAULT, PLACEHOLDERS_CLASIFICACION,
    validar_prompt_clasificacion,
)
from captura import (
    PROMPT_IMAGEN_ACTIVIDAD_DEFAULT, PROMPT_IMAGEN_REUNION_DEFAULT,
    PLACEHOLDERS_IMAGEN, validar_prompt_imagen,
)
from proyectos import (
    crear_md_proyecto, ruta_md_proyecto, listar_proyectos_con_md,
    migrar_bitacoras_antiguas, _slugify
)
from cliente_ia import (
    MODELOS_DISPONIBLES, PROVEEDORES, MODELOS_PRINCIPALES,
    get_cliente
)
import temas


# ---------------------------------------------------------------------------
# Iconos de la aplicación
# ---------------------------------------------------------------------------
# Los iconos viven en la carpeta `assets/` junto a los .py del agente:
#   - assets/agente.ico   → barra de tareas (set en agente.py vía app.setWindowIcon)
#   - assets/ventana.ico  → ventana principal, popups y systray
# La carga es defensiva: si un .ico no existe, se devuelve un QIcon vacío
# y se loguea la advertencia, sin reventar el arranque del agente.

_DIR_ASSETS = Path(__file__).parent / "assets"


def _resolver_icono(nombre_archivo: str) -> QIcon:
    """
    Devuelve un QIcon a partir de un archivo en assets/.
    Si el archivo no existe, retorna un QIcon vacío y avisa por consola.
    Esto permite que el agente arranque aunque falte el archivo.
    """
    ruta = _DIR_ASSETS / nombre_archivo
    if not ruta.exists():
        print(f"[Iconos] ⚠ No se encontró {ruta} — usando icono por defecto.")
        return QIcon()
    icono = QIcon(str(ruta))
    if icono.isNull():
        print(f"[Iconos] ⚠ {ruta} no se pudo cargar como QIcon — usando default.")
        return QIcon()
    return icono




# ---------------------------------------------------------------------------
# Stylesheets parametrizados por tema
# ---------------------------------------------------------------------------
# Cada función toma una paleta (dict de colores) y devuelve el CSS de un
# bloque concreto. La paleta se obtiene de temas.obtener_paleta_activa().
#
# Para cambiar de tema en caliente: cambiar el campo `tema_visual` en
# config.json, luego llamar a `_aplicar_tema_a_widgets_abiertos(ventana)`.
#
# Si añades un nuevo color hardcoded a un stylesheet, mapéalo a un campo
# de la paleta — nunca uses #xxxxxx literales aquí.
# ---------------------------------------------------------------------------

def _stylesheet_ventana_principal(p: dict) -> str:
    """CSS de la VentanaAgente (la ventana flotante principal)."""
    return f"""
        QWidget {{
            background-color: {p["fondo_principal"]};
            color: {p["texto_principal"]};
            font-family: 'Segoe UI';
        }}
        QLabel#subtitulo {{ color: {p["texto_subtitulo"]}; font-size: 8pt; }}
        QLabel#badge {{ color: {p["acento"]}; font-size: 8pt; font-weight: bold; }}
        QLineEdit {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QTextEdit {{
            background-color: {p["fondo_secundario"]};
            border: 1px solid {p["fondo_terciario"]};
            border-radius: 4px;
            color: {p["selector_acento"]};
        }}
        QPushButton {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 12px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: {p["fondo_hover"]}; }}
        QPushButton:checked {{
            background-color: {p["acento"]};
            color: {p["texto_inverso"]};
            font-weight: bold;
        }}
        QPushButton:disabled {{ color: {p["texto_atenuado"]}; border-color: {p["fondo_terciario"]}; }}
        QScrollBar:vertical {{
            background: {p["fondo_secundario"]};
            width: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {p["borde"]};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p["scroll_handle"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

        QPushButton#btn_chat_activo {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["acento"]};
            color: {p["acento"]};
        }}
    """


def _stylesheet_menu_monitores(p: dict) -> str:
    """CSS del menú contextual del selector de monitor."""
    return f"""
        QMenu {{
            background-color: {p["fondo_terciario"]};
            color: {p["texto_principal"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 4px;
            font-family: 'Segoe UI';
            font-size: 9pt;
        }}
        QMenu::item {{
            padding: 6px 16px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {p["fondo_hover"]};
        }}
        QMenu::item:checked {{
            color: {p["exito"]};
            font-weight: bold;
        }}
    """


def _stylesheet_popup_nota(p: dict) -> str:
    """CSS del PopupNota (pequeño popup de captura)."""
    return f"""
        QDialog, QWidget {{
            background-color: {p["fondo_principal"]};
            color: {p["texto_principal"]};
            font-family: 'Segoe UI';
        }}
        QLabel {{ color: {p["texto_principal"]}; font-size: 9pt; }}
        QLabel#subtitulo {{ color: {p["texto_subtitulo"]}; font-size: 8pt; }}
        QLineEdit, QTextEdit {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 7px 14px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: {p["fondo_hover"]}; }}
    """


def _stylesheet_popup_proyectos(p: dict) -> str:
    """CSS del PopupProyectos (gestor con lista de activos+cerrados)."""
    return f"""
        QDialog, QWidget {{
            background-color: {p["fondo_principal"]};
            color: {p["texto_principal"]};
            font-family: 'Segoe UI';
        }}
        QLabel {{ color: {p["texto_principal"]}; font-size: 9pt; }}
        QLabel#subtitulo {{ color: {p["texto_subtitulo"]}; font-size: 8pt; }}
        QLineEdit, QTextEdit {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 7px 14px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: {p["fondo_hover"]}; }}
        QPushButton#btn_nuevo {{
            background-color: {p["exito"]};
            color: {p["texto_inverso"]};
            font-weight: bold;
        }}
        QPushButton#btn_cerrar_proyecto {{
            background-color: {p["peligro"]};
            color: {p["texto_inverso"]};
        }}
        QPushButton#btn_activar_proyecto {{
            background-color: {p["exito"]};
            color: {p["texto_inverso"]};
        }}
        QLabel#nombre_cerrado {{ color: {p["texto_subtitulo"]}; }}
        QLabel#subtitulo_cerrado {{ color: {p["texto_atenuado"]}; font-size: 8pt; }}
        QScrollArea#scroll_proyectos {{
            background-color: {p["fondo_principal"]};
            border: none;
        }}
        QScrollBar:vertical {{
            background-color: {p["fondo_principal"]};
            width: 10px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {p["borde"]};
            border-radius: 5px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {p["scroll_handle"]};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background-color: transparent;
        }}
    """


def _stylesheet_popup_gantt(p: dict) -> str:
    """CSS del PopupGantt (selector de gantt a abrir)."""
    return f"""
        QDialog, QWidget {{
            background-color: {p["fondo_principal"]};
            color: {p["texto_principal"]};
            font-family: 'Segoe UI';
        }}
        QLabel {{ color: {p["texto_principal"]}; font-size: 9pt; }}
        QPushButton {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 8px 14px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: {p["fondo_hover"]}; }}
        QPushButton#btn_global {{
            background-color: {p["acento"]};
            color: {p["texto_inverso"]};
            font-weight: bold;
        }}
        QPushButton#btn_global:hover {{ background-color: {p["scroll_handle_hover"]}; }}
        QComboBox {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QComboBox:hover {{ border-color: {p["borde_hover"]}; }}
        QComboBox QAbstractItemView {{
            background-color: {p["fondo_terciario"]};
            color: {p["texto_principal"]};
            selection-background-color: {p["fondo_hover"]};
        }}
    """


def _stylesheet_popup_configuraciones(p: dict) -> str:
    """CSS del PopupConfiguraciones (el más grande, con todas las secciones)."""
    return f"""
        QDialog, QWidget {{
            background-color: {p["fondo_principal"]};
            color: {p["texto_principal"]};
            font-family: 'Segoe UI';
        }}
        QLabel {{ color: {p["texto_principal"]}; font-size: 9pt; }}
        QLabel#titulo_seccion {{
            color: {p["acento"]};
            margin-top: 4px;
        }}
        QLabel#hint {{
            color: {p["texto_subtitulo"]};
            font-size: 8pt;
        }}
        QTextEdit, QLineEdit {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 6px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QSpinBox {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 4px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: {p["fondo_hover"]};
            width: 18px;
            border-radius: 3px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {p["scroll_handle"]};
        }}
        QComboBox {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 4px 10px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QComboBox:hover {{ border-color: {p["borde_hover"]}; }}
        QComboBox QAbstractItemView {{
            background-color: {p["fondo_terciario"]};
            color: {p["texto_principal"]};
            selection-background-color: {p["fondo_hover"]};
            border: 1px solid {p["borde"]};
        }}
        QPushButton {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 6px;
            padding: 8px 16px;
            color: {p["texto_principal"]};
            font-size: 9pt;
        }}
        QPushButton:hover {{ background-color: {p["fondo_hover"]}; }}
        QPushButton#btn_guardar {{
            background-color: {p["exito"]};
            color: {p["texto_inverso"]};
            font-weight: bold;
        }}
        QPushButton#btn_guardar:hover {{ background-color: {p["exito_hover"]}; }}
        QPushButton#btn_limpiar_finops {{
            background-color: {p["peligro"]};
            color: {p["texto_inverso"]};
        }}
        QPushButton#btn_limpiar_finops:hover {{ background-color: {p["peligro_hover"]}; }}
        QPushButton#btn_preview_tema {{
            background-color: {p["acento"]};
            color: {p["texto_inverso"]};
            font-weight: bold;
        }}
        QFrame#tarjeta_finops {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 8px;
        }}
        QLabel#titulo_tarjeta_finops {{
            color: {p["acento"]};
            font-weight: bold;
            font-size: 9pt;
        }}
        QLabel#costo_tarjeta_finops {{
            color: {p["exito"]};
            font-weight: bold;
            font-size: 16pt;
        }}
        QFrame#grafico_finops {{
            background-color: {p["fondo_terciario"]};
            border: 1px solid {p["borde"]};
            border-radius: 8px;
        }}
        QProgressBar#barra_finops {{
            background-color: {p["fondo_principal"]};
            border: 1px solid {p["borde"]};
            border-radius: 5px;
        }}
        QProgressBar#barra_finops::chunk {{
            background-color: {p["acento"]};
            border-radius: 4px;
        }}
        QFrame#barra_inferior {{
            background-color: {p["fondo_secundario"]};
            border-top: 1px solid {p["fondo_terciario"]};
        }}
        QScrollBar:vertical {{
            background: {p["fondo_secundario"]};
            width: 8px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: {p["borde"]};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {p["scroll_handle"]}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    """




# ---------------------------------------------------------------------------
# QTextEdit con handle de arrastre en el borde inferior
# ---------------------------------------------------------------------------
class TextEditRedimensionable(QTextEdit):
    """
    QTextEdit que permite redimensionar su alto arrastrando el borde inferior.
    Muestra un pequeño handle visual y cambia el cursor al pasar por la zona.
    """
    HANDLE_HEIGHT = 6  # ← DIMENSIÓN: grosor de la zona de arrastre inferior (px)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._arrastrando = False
        self._y_inicio = 0
        self._alto_inicio = 0
        self._min_alto = 30                      # ← DIMENSIÓN: alto mínimo absoluto del recuadro
        self.setMouseTracking(True)
        self.setMinimumHeight(self._min_alto)

    def _en_zona_handle(self, pos_y: int) -> bool:
        """Retorna True si el mouse está en la zona de arrastre inferior."""
        return pos_y >= self.height() - self.HANDLE_HEIGHT

    def mousePressEvent(self, event):
        if self._en_zona_handle(event.pos().y()) and event.button() == Qt.LeftButton:
            self._arrastrando = True
            self._y_inicio = event.globalPos().y()
            self._alto_inicio = self.height()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._arrastrando:
            delta = event.globalPos().y() - self._y_inicio
            nuevo_alto = max(self._min_alto, self._alto_inicio + delta)
            self.setFixedHeight(nuevo_alto)
            event.accept()
        elif self._en_zona_handle(event.pos().y()):
            self.viewport().setCursor(Qt.SizeVerCursor)
            event.accept()
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._arrastrando:
            self._arrastrando = False
            alto_final = self.height()
            # Restaurar min/max para que Qt no quede bloqueado
            self.setMinimumHeight(self._min_alto)
            self.setMaximumHeight(16777215)
            self.setFixedHeight(alto_final)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Dibujar línea sutil del handle (color del borde según tema activo)
        from PyQt5.QtGui import QPainter, QPen
        painter = QPainter(self.viewport())
        pen = QPen(QColor(temas.obtener_paleta_activa()["borde"]))
        pen.setWidth(1)
        painter.setPen(pen)
        y = self.viewport().height() - 2
        x_center = self.viewport().width() // 2
        painter.drawLine(x_center - 20, y, x_center + 20, y)  # ← DIMENSIÓN: ancho del indicador visual
        painter.end()

# ---------------------------------------------------------------------------
# Señales para comunicación entre hilos
# ---------------------------------------------------------------------------
class Senales(QObject):
    nueva_entrada   = pyqtSignal(dict)  # Monitor detectó cambio
    actualizar_ui   = pyqtSignal(str)   # Mensaje de estado
    respuesta_chat  = pyqtSignal(str)   # Respuesta de Claude lista
    error_chat      = pyqtSignal(str)   # Error en chat
    alerta_gantt    = pyqtSignal(str)   # Alertas de inactividad


# ---------------------------------------------------------------------------
# Popup de nota post-captura
# ---------------------------------------------------------------------------
class PopupNota(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar nota a la captura")
        self.setWindowIcon(_resolver_icono("ventana.ico"))
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Captura realizada ✅\nAgrega una nota opcional:"))

        self.campo_nota = QTextEdit()
        self.campo_nota.setPlaceholderText("Describe qué muestra esta captura...")
        self.campo_nota.setMaximumHeight(80)
        layout.addWidget(self.campo_nota)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def obtener_nota(self) -> str:
        return self.campo_nota.toPlainText().strip()


# ---------------------------------------------------------------------------
# Hilo para análisis de imagen en background (no bloquea la UI)
# ---------------------------------------------------------------------------
class _AnalizadorImagenThread(QThread):
    """
    Ejecuta el análisis del LLM en un hilo separado para que la UI no se
    congele mientras esperamos la respuesta de la API.

    Uso típico:
        thread = _AnalizadorImagenThread(analizar_fn, titulo, imagen_b64)
        thread.start()
        # ... la UI sigue respondiendo ...
        thread.wait()  # bloquea solo cuando realmente lo necesitas
        resultado = thread.resultado
    """
    terminado = pyqtSignal(dict)

    def __init__(self, analizar_fn, titulo: str, imagen_b64: str):
        super().__init__()
        self._analizar_fn = analizar_fn
        self._titulo = titulo
        self._imagen_b64 = imagen_b64
        self.resultado = None
        self.error = None

    def run(self):
        try:
            self.resultado = self._analizar_fn(self._titulo, False, self._imagen_b64)
        except Exception as e:
            self.error = str(e)
            self.resultado = {
                "actividad": f"Error al analizar: {str(e)[:80]}",
                "categoria": "Error",
                "herramienta": self._titulo
            }
        self.terminado.emit(self.resultado)


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------
class VentanaAgente(QWidget):

    def __init__(self, senales: Senales, gestor_bitacora=None, capturar_fn=None):
        super().__init__()
        self.senales         = senales
        self.gestor_bitacora = gestor_bitacora
        self.capturar_fn     = capturar_fn
        self.config          = cargar_config()
        self._anclada        = self.config.get("ventana_anclada", False)
        self._pausado        = False
        self._chat_visible   = False
        self._alto_pre_chat  = 560               # Alto antes de expandir chat
        self._ventana_actual = "—"
        self._hora_inicio    = datetime.now()
        self.gestor_chat     = GestorChat()

        self._construir_ui()
        self._aplicar_estilo()
        self._configurar_tray()
        self._configurar_timers()

        # Conectar señales
        self.senales.nueva_entrada.connect(self._on_nueva_entrada)
        self.senales.actualizar_ui.connect(self._on_mensaje_estado)
        self.senales.respuesta_chat.connect(self._on_respuesta_chat)
        self.senales.error_chat.connect(self._on_error_chat)
        self.senales.alerta_gantt.connect(self._on_alerta_gantt)

        self._aplicar_anclaje()

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _construir_ui(self):
        self.setWindowTitle("El Egypcio")
        self.setWindowIcon(_resolver_icono("ventana.ico"))
        self.setMinimumWidth(340)                # ← DIMENSIÓN: ancho mínimo ventana (px)
        self.setMinimumHeight(480)               # ← DIMENSIÓN: alto mínimo ventana (px)
        self.resize(400, 560)                    # ← DIMENSIÓN: tamaño inicial ventana (ancho, alto)
        self._primera_muestra = True             # Flag para showEvent

        # --- ScrollArea para que el chat no quede cortado ---
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._contenedor = QWidget()
        self.root = QVBoxLayout(self._contenedor)
        self.root.setContentsMargins(10, 8, 10, 10)  # ← DIMENSIÓN: márgenes internos (izq, top, der, bot)
        self.root.setSpacing(6)                  # ← DIMENSIÓN: espacio entre elementos (px)

        # --- Barra superior ---
        barra = QHBoxLayout()
        self.lbl_estado = QLabel("🟢 Activo")
        self.lbl_estado.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.lbl_hora = QLabel()
        self.lbl_hora.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_hora.setFont(QFont("Segoe UI", 9))
        self.btn_anclar = QPushButton("📌")
        self.btn_anclar.setFixedSize(40, 36)     # ← DIMENSIÓN: tamaño botón anclar (ancho, alto)
        self.btn_anclar.setToolTip("Mantener siempre visible")
        self.btn_anclar.setCheckable(True)
        self.btn_anclar.setChecked(self._anclada)
        self.btn_anclar.clicked.connect(self._toggle_anclaje)

        self.btn_config = QPushButton("⚙")
        self.btn_config.setFixedSize(40, 36)     # ← DIMENSIÓN: tamaño botón configuraciones
        self.btn_config.setToolTip("Configuraciones del agente")
        self.btn_config.clicked.connect(self._abrir_configuraciones)

        # Botón selector de monitor
        self.btn_monitor = QPushButton("🖥")
        self.btn_monitor.setFixedSize(40, 36)    # ← DIMENSIÓN: tamaño botón monitor
        self.btn_monitor.setToolTip("Seleccionar monitor a capturar")
        self.btn_monitor.clicked.connect(self._mostrar_menu_monitor)
        self._actualizar_estado_monitor()

        barra.addWidget(self.lbl_estado)
        barra.addStretch()
        barra.addWidget(self.lbl_hora)
        barra.addWidget(self.btn_anclar)
        barra.addWidget(self.btn_monitor)
        barra.addWidget(self.btn_config)
        self.root.addLayout(barra)
        self.root.addWidget(self._separador())

        # --- Panel actividad actual ---
        self.lbl_actividad_titulo = QLabel("Actividad actual")
        self.lbl_actividad_titulo.setObjectName("subtitulo")
        self.lbl_ventana = QLabel("—")
        self.lbl_ventana.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.lbl_ventana.setWordWrap(True)
        self.lbl_duracion = QLabel("⏱ —")
        self.lbl_duracion.setObjectName("subtitulo")
        self.lbl_categoria = QLabel("")
        self.lbl_categoria.setObjectName("badge")
        fila_meta = QHBoxLayout()
        fila_meta.addWidget(self.lbl_duracion)
        fila_meta.addStretch()
        fila_meta.addWidget(self.lbl_categoria)
        self.root.addWidget(self.lbl_actividad_titulo)
        self.root.addWidget(self.lbl_ventana)
        self.root.addLayout(fila_meta)
        self.root.addWidget(self._separador())

        # --- Log de actividad ---
        self.lbl_log_titulo = QLabel("Registro de hoy")
        self.lbl_log_titulo.setObjectName("subtitulo")
        self.root.addWidget(self.lbl_log_titulo)
        self.txt_log = TextEditRedimensionable()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(60)        # ← DIMENSIÓN: alto mínimo del log de actividad
        self.txt_log.setFixedHeight(100)         # ← DIMENSIÓN: alto inicial del log de actividad
        self.txt_log.setFont(QFont("Consolas", 8))
        self.txt_log.setPlaceholderText("Las actividades detectadas aparecerán aquí...")
        self.root.addWidget(self.txt_log)
        self.root.addWidget(self._separador())

        # --- Comentario rápido ---
        self.lbl_comentario = QLabel("Agregar nota a actividad actual")
        self.lbl_comentario.setObjectName("subtitulo")
        self.root.addWidget(self.lbl_comentario)
        fila_nota = QHBoxLayout()
        self.campo_nota = QLineEdit()
        self.campo_nota.setPlaceholderText("Escribe una nota rápida... (@ para tipos)")
        self.campo_nota.returnPressed.connect(self._agregar_nota)

        # Autocompletado de prefijos estructurados (Fase 5)
        # Los prefijos se sugieren cuando el usuario escribe "@" al inicio
        self._prefijos_nota = [
            "@decision: ",
            "@tarea: ",
            "@acuerdo: ",
            "@idea: ",
            "@bloqueado: ",
            "@ticket: ",
            "@pendiente: ",
            "@objeto: ",
            "@diccionario: ",
            "@persona: ",
        ]
        self._completer_nota = QCompleter(self._prefijos_nota, self.campo_nota)
        self._completer_nota.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer_nota.setFilterMode(Qt.MatchStartsWith)
        self._completer_nota.setCompletionMode(QCompleter.PopupCompletion)
        self.campo_nota.setCompleter(self._completer_nota)

        self.btn_nota = QPushButton("➕")
        self.btn_nota.setFixedSize(30, 30)       # ← DIMENSIÓN: tamaño botón agregar nota
        self.btn_nota.clicked.connect(self._agregar_nota)
        fila_nota.addWidget(self.campo_nota)
        fila_nota.addWidget(self.btn_nota)
        self.root.addLayout(fila_nota)

        # --- Botones de acción ---
        fila_acciones = QHBoxLayout()
        self.btn_captura = QPushButton("📷 Capturar")
        self.btn_captura.clicked.connect(self._captura_manual)
        self.btn_pausar = QPushButton("⏸ Pausar")
        self.btn_pausar.setCheckable(True)
        self.btn_pausar.clicked.connect(self._toggle_pausa)
        fila_acciones.addWidget(self.btn_captura)
        fila_acciones.addWidget(self.btn_pausar)
        self.root.addLayout(fila_acciones)

        # --- Botones de navegación ---
        fila_nav = QHBoxLayout()
        self.btn_bitacora = QPushButton("📋 Bitácora")
        self.btn_bitacora.clicked.connect(self._abrir_bitacora)
        self.btn_gantt = QPushButton("📊 Gantt")
        self.btn_gantt.setToolTip("Ver diagrama Gantt de proyectos")
        self.btn_gantt.clicked.connect(self._abrir_gantt)
        fila_nav.addWidget(self.btn_bitacora)
        fila_nav.addWidget(self.btn_gantt)
        self.root.addLayout(fila_nav)

        # --- Botón gestión de proyectos ---
        self.btn_proyectos = QPushButton("🗂 Gestionar proyectos")
        self.btn_proyectos.clicked.connect(self._abrir_proyectos)
        self.root.addWidget(self.btn_proyectos)

        self.root.addWidget(self._separador())

        # --- Botón expandir chat ---
        self.btn_chat = QPushButton("💬 Consultar al agente  ▼")
        self.btn_chat.setCheckable(True)
        self.btn_chat.clicked.connect(self._toggle_chat)
        self.root.addWidget(self.btn_chat)

        # --- Panel de chat (oculto por defecto, con splitter) ---
        self.panel_chat = QWidget()
        self.panel_chat.setVisible(False)
        layout_chat = QVBoxLayout(self.panel_chat)
        layout_chat.setContentsMargins(0, 4, 0, 0)
        layout_chat.setSpacing(4)

        # Historial del chat
        self.txt_chat = TextEditRedimensionable()
        self.txt_chat.setReadOnly(True)
        self.txt_chat.setMinimumHeight(80)       # ← DIMENSIÓN: alto mínimo del chat
        self.txt_chat.setFixedHeight(160)        # ← DIMENSIÓN: alto inicial del chat
        self.txt_chat.setFont(QFont("Segoe UI", 9))
        self.txt_chat.setPlaceholderText("Hazle una pregunta al agente sobre tu jornada...")
        layout_chat.addWidget(self.txt_chat)

        # Botones rápidos
        fila_rapidos = QHBoxLayout()
        self.btn_resumen_dia = QPushButton("📋 Resumen hoy")
        self.btn_resumen_dia.clicked.connect(self._resumen_dia)
        self.btn_resumen_semana = QPushButton("📊 Resumen semana")
        self.btn_resumen_semana.clicked.connect(self._resumen_semana)
        self.btn_limpiar_chat = QPushButton("🗑 Limpiar")
        self.btn_limpiar_chat.setFixedWidth(70)  # ← DIMENSIÓN: ancho botón Limpiar
        self.btn_limpiar_chat.clicked.connect(self._limpiar_chat)
        fila_rapidos.addWidget(self.btn_resumen_dia)
        fila_rapidos.addWidget(self.btn_resumen_semana)
        fila_rapidos.addWidget(self.btn_limpiar_chat)
        layout_chat.addLayout(fila_rapidos)

        # Campo de entrada del chat
        fila_entrada = QHBoxLayout()
        self.campo_chat = QLineEdit()
        self.campo_chat.setPlaceholderText("Escribe tu pregunta...")
        self.campo_chat.returnPressed.connect(self._enviar_mensaje)
        self.btn_enviar = QPushButton("↵")
        self.btn_enviar.setFixedSize(50, 36)     # ← DIMENSIÓN: tamaño botón enviar chat
        self.btn_enviar.setToolTip("Enviar mensaje")
        self.btn_enviar.clicked.connect(self._enviar_mensaje)
        fila_entrada.addWidget(self.campo_chat)
        fila_entrada.addWidget(self.btn_enviar)
        layout_chat.addLayout(fila_entrada)

        self.root.addWidget(self.panel_chat)

        # Montar contenedor en scroll y scroll en ventana
        self._scroll.setWidget(self._contenedor)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Estilo visual
    # ------------------------------------------------------------------
    def _aplicar_estilo(self):
        """
        Aplica el stylesheet del tema activo. Se puede re-llamar para refrescar
        el aspecto cuando el usuario cambia de tema en caliente.
        """
        paleta = temas.obtener_paleta_activa()
        self.setStyleSheet(_stylesheet_ventana_principal(paleta))

    # ------------------------------------------------------------------
    # System Tray
    # ------------------------------------------------------------------
    def _configurar_tray(self):
        # Icono: prioridad al .ico real. Si no existe, fallback a un cuadro de
        # color (comportamiento original) para que el tray no quede invisible.
        icono = _resolver_icono("ventana.ico")
        if icono.isNull():
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("#a6e3a1"))
            icono = QIcon(pixmap)
        self.tray = QSystemTrayIcon(icono, self)
        self.tray.setToolTip("Agente LLM - El Egypcio")
        menu_tray = QMenu()
        accion_mostrar  = QAction("Mostrar ventana", self)
        accion_pausar   = QAction("Pausar agente", self)
        accion_bitacora = QAction("Abrir bitácora", self)
        accion_cerrar   = QAction("Cerrar agente", self)
        accion_mostrar.triggered.connect(self.showNormal)
        accion_pausar.triggered.connect(self._toggle_pausa)
        accion_bitacora.triggered.connect(self._abrir_bitacora)
        accion_cerrar.triggered.connect(self._cerrar_agente)
        menu_tray.addAction(accion_mostrar)
        menu_tray.addAction(accion_pausar)
        menu_tray.addSeparator()
        menu_tray.addAction(accion_bitacora)
        menu_tray.addSeparator()
        menu_tray.addAction(accion_cerrar)
        self.tray.setContextMenu(menu_tray)
        self.tray.activated.connect(self._on_tray_click)
        self.tray.show()

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------
    def _configurar_timers(self):
        self.timer_hora = QTimer(self)
        self.timer_hora.timeout.connect(self._actualizar_hora)
        self.timer_hora.start(1000)
        self.timer_duracion = QTimer(self)
        self.timer_duracion.timeout.connect(self._actualizar_duracion)
        self.timer_duracion.start(30000)

    # ------------------------------------------------------------------
    # Slots — actividad
    # ------------------------------------------------------------------
    def _on_nueva_entrada(self, analisis: dict):
        titulo    = analisis.get("titulo_ventana", "—")[:55]
        categoria = analisis.get("categoria", "")
        es_reunion = analisis.get("es_reunion", False)
        self._ventana_actual = titulo
        self._hora_inicio    = datetime.now()
        self.lbl_ventana.setText(titulo)
        self.lbl_categoria.setText("🎥 Reunión" if es_reunion else categoria)
        self.lbl_duracion.setText("⏱ < 1 min")
        hora = datetime.now().strftime("%H:%M")
        self.txt_log.append(f"[{hora}] {categoria} — {titulo[:35]}\n")
        self.txt_log.ensureCursorVisible()

    def _on_mensaje_estado(self, mensaje: str):
        self.lbl_estado.setText(mensaje)

    def _actualizar_hora(self):
        self.lbl_hora.setText(datetime.now().strftime("%H:%M:%S"))

    def _actualizar_duracion(self):
        if self._hora_inicio:
            minutos = int((datetime.now() - self._hora_inicio).total_seconds() // 60)
            self.lbl_duracion.setText(f"⏱ {minutos} min" if minutos > 0 else "⏱ < 1 min")

    def _agregar_nota(self):
        texto = self.campo_nota.text().strip()
        if not texto:
            return
        if self.gestor_bitacora:
            self.gestor_bitacora.agregar_comentario(texto)
        self.txt_log.append(f"  💬 Nota: {texto}\n")
        self.campo_nota.clear()

    def _captura_manual(self):
        """
        Flujo de captura manual optimizado:
        1. Screenshot local INMEDIATO (~200ms) — guarda PNG y obtiene base64
        2. Popup de nota aparece YA (sin esperar al LLM)
        3. Mientras escribes la nota, el LLM analiza la imagen en background
        4. Al confirmar la nota, se espera al LLM si aún no terminó
        5. Se escribe la entrada en la bitácora (con imagen + análisis + nota)

        Esto elimina los segundos de espera al hacer click en el botón.
        """
        if not self.capturar_fn:
            return

        # Importar aquí para no romper si captura.py se actualiza independiente
        try:
            from captura import tomar_screenshot_y_guardar, analizar_screenshot
        except ImportError as e:
            self.txt_log.append(f"  ⚠️ Error: {e}\n")
            return

        self.btn_captura.setEnabled(False)
        self.btn_captura.setText("📷 Capturando...")
        QApplication.processEvents()  # forzar refresco visual del botón

        thread = None
        try:
            # PASO 1: Screenshot local + guardado en disco (rápido, ~200ms)
            ruta_imagen, imagen_b64 = tomar_screenshot_y_guardar()

            # PASO 2: Lanzar análisis del LLM en hilo separado
            thread = _AnalizadorImagenThread(
                analizar_screenshot, self._ventana_actual, imagen_b64
            )
            thread.start()

            # PASO 3: Mostrar popup INMEDIATAMENTE (no esperamos al LLM)
            self.btn_captura.setText("📷 Analizando...")
            popup = PopupNota(self)
            nota = popup.obtener_nota() if popup.exec_() == QDialog.Accepted else ""

            # PASO 4: Esperar a que el LLM termine si aún sigue corriendo
            if thread.isRunning():
                self.btn_captura.setText("📷 Esperando análisis...")
                QApplication.processEvents()
                thread.wait(30000)  # máximo 30s

            analisis = thread.resultado or {}
            descripcion = analisis.get("actividad", "Captura manual")

            # PASO 5: Persistir en bitácora con la imagen
            if self.gestor_bitacora:
                self.gestor_bitacora.agregar_captura_manual(
                    descripcion, nota,
                    ruta_imagen=ruta_imagen,
                    titulo_ventana=self._ventana_actual
                )
            self.txt_log.append("  📷 Captura manual registrada\n")

        except Exception as e:
            self.txt_log.append(f"  ⚠️ Error en captura: {e}\n")
        finally:
            # Asegurar limpieza del hilo aunque algo falle
            if thread is not None and thread.isRunning():
                thread.wait(5000)
            self.btn_captura.setEnabled(True)
            self.btn_captura.setText("📷 Capturar")

    def _toggle_pausa(self):
        self._pausado = not self._pausado
        if self._pausado:
            self.lbl_estado.setText("🟡 Pausado")
            self.btn_pausar.setText("▶ Reanudar")
            self.tray.setToolTip("Agente LLM - El Egypcio (Pausado)")
        else:
            self.lbl_estado.setText("🟢 Activo")
            self.btn_pausar.setText("⏸ Pausar")
            self.tray.setToolTip("Agente LLM - El Egypcio")

    def _toggle_anclaje(self):
        self._anclada = self.btn_anclar.isChecked()
        self._aplicar_anclaje()
        try:
            import json
            ruta = Path(__file__).parent / "config.json"
            with open(ruta, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["ventana_anclada"] = self._anclada
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _aplicar_anclaje(self):
        flags = self.windowFlags()
        if self._anclada:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    def _abrir_bitacora(self):
        config = cargar_config()
        app_bitacora = config.get("app_bitacora", "auto")
        ruta_base = ruta_bitacoras()
        fecha = datetime.now().strftime("%Y-%m-%d")
        archivo = ruta_base / f"bitacora_{fecha}.md"

        if app_bitacora == "obsidian":
            ruta_1 = config.get("ruta_obsidian_1", "")
            ruta_2 = config.get("ruta_obsidian_2", "")

            # El archivo vive en bitacoras/ dentro del vault. El URI usa el
            # nombre real del vault (derivado de ruta_base), no "bitacoras".
            uri = uri_obsidian(f"bitacoras/bitacora_{fecha}")
            if Path(ruta_1).exists() or Path(ruta_2).exists():
                os.startfile(uri)
            else:
                subprocess.Popen(["explorer", str(ruta_base)], shell=True)
        elif app_bitacora == "vscode":
            subprocess.Popen(["code", str(archivo)], shell=True)
        else:
            # auto: intenta VS Code, si falla abre la carpeta
            try:
                subprocess.Popen(["code", str(archivo)], shell=True)
            except Exception:
                subprocess.Popen(["explorer", str(ruta_base)], shell=True)

    # ------------------------------------------------------------------
    # Slots — Chat
    # ------------------------------------------------------------------
    def _toggle_chat(self):
        self._chat_visible = not self._chat_visible
        self.panel_chat.setVisible(self._chat_visible)
        if self._chat_visible:
            self.btn_chat.setText("💬 Consultar al agente  ▲")
            self._alto_pre_chat = self.height()   # Guardar alto antes de expandir
            self.resize(self.width(), self.height() + 280)  # ← DIMENSIÓN: expansión al abrir chat
        else:
            self.btn_chat.setText("💬 Consultar al agente  ▼")
            self.panel_chat.setVisible(False)
            self.resize(self.width(), self._alto_pre_chat)  # Restaurar alto original

    def _set_chat_cargando(self, cargando: bool):
        """Bloquea/desbloquea los controles del chat mientras Claude responde."""
        self.campo_chat.setEnabled(not cargando)
        self.btn_enviar.setEnabled(not cargando)
        self.btn_resumen_dia.setEnabled(not cargando)
        self.btn_resumen_semana.setEnabled(not cargando)
        if cargando:
            self.txt_chat.append("\n⏳ Consultando al agente...\n")
            self.txt_chat.ensureCursorVisible()

    def _enviar_mensaje(self):
        pregunta = self.campo_chat.text().strip()
        if not pregunta:
            return
        self.txt_chat.append(f"\n🧑 **Tú:** {pregunta}\n")
        self.campo_chat.clear()
        self._set_chat_cargando(True)

        def callback(respuesta, error):
            if error:
                self.senales.error_chat.emit(f"Error: {error}")
            else:
                self.senales.respuesta_chat.emit(respuesta)

        self.gestor_chat.responder(pregunta, callback)

    def _resumen_dia(self):
        self._set_chat_cargando(True)
        self.txt_chat.append("\n📋 **Generando resumen del día...**\n")

        def callback(respuesta, error):
            if error:
                self.senales.error_chat.emit(f"Error: {error}")
            else:
                self.senales.respuesta_chat.emit(respuesta)

        self.gestor_chat.generar_resumen_dia(callback)

    def _resumen_semana(self):
        self._set_chat_cargando(True)
        self.txt_chat.append("\n📊 **Generando resumen semanal...**\n")

        def callback(respuesta, error):
            if error:
                self.senales.error_chat.emit(f"Error: {error}")
            else:
                self.senales.respuesta_chat.emit(respuesta)

        self.gestor_chat.generar_resumen_semana(callback)

    def _on_respuesta_chat(self, respuesta: str):
        # Limpiar el mensaje de "cargando"
        texto_actual = self.txt_chat.toPlainText()
        if "⏳ Consultando al agente..." in texto_actual:
            cursor = self.txt_chat.textCursor()
            texto_limpio = texto_actual.replace("\n⏳ Consultando al agente...\n", "")
            self.txt_chat.setPlainText(texto_limpio)

        self.txt_chat.append(f"\n🤖 **Agente:**\n{respuesta}\n")
        self.txt_chat.ensureCursorVisible()
        self._set_chat_cargando(False)

    def _on_error_chat(self, error: str):
        self.txt_chat.append(f"\n⚠️ {error}\n")
        self.txt_chat.ensureCursorVisible()
        self._set_chat_cargando(False)

    def _limpiar_chat(self):
        self.txt_chat.clear()
        self.gestor_chat.limpiar_historial()

    # ------------------------------------------------------------------
    # Tray y cierre
    # ------------------------------------------------------------------
    def _abrir_gantt(self):
        """Abre el popup de selección de Gantt (global o por proyecto)."""
        popup = PopupGantt(self)
        popup.exec_()

    def _on_alerta_gantt(self, mensaje: str):
        """Muestra alertas de inactividad en el chat al iniciar."""
        if not self._chat_visible:
            self._toggle_chat()
        self.txt_chat.append("\n" + mensaje + "\n")
        self.txt_chat.ensureCursorVisible()

    def _abrir_proyectos(self):
        """Abre el popup de gestión de proyectos."""
        popup = PopupProyectos(self)
        popup.exec_()

    # ------------------------------------------------------------------
    # Selector de monitor
    # ------------------------------------------------------------------
    def _detectar_monitores(self) -> list:
        """Detecta los monitores conectados usando mss."""
        try:
            import mss
            with mss.mss() as sct:
                # sct.monitors[0] = todos juntos, [1] = principal, [2] = secundario...
                monitores = []
                for i, m in enumerate(sct.monitors):
                    if i == 0:
                        continue  # Índice 0 es el combinado, lo manejamos aparte
                    ancho = m["width"]
                    alto  = m["height"]
                    etiqueta = "Principal" if i == 1 else f"Secundario"
                    monitores.append({
                        "indice": i,
                        "nombre": f"Monitor {i} ({etiqueta} — {ancho}×{alto})",
                        "ancho": ancho,
                        "alto": alto
                    })
                return monitores
        except ImportError:
            print("[Ventana] mss no instalado — pip install mss")
            return []
        except Exception as e:
            print(f"[Ventana] Error detectando monitores: {e}")
            return []

    def _actualizar_estado_monitor(self):
        """Habilita/deshabilita el botón de monitor según cuántos hay."""
        monitores = self._detectar_monitores()
        if len(monitores) <= 1:
            self.btn_monitor.setEnabled(False)
            self.btn_monitor.setToolTip("Solo 1 monitor detectado")
        else:
            self.btn_monitor.setEnabled(True)
            self.btn_monitor.setToolTip("Seleccionar monitor a capturar")

    def _mostrar_menu_monitor(self):
        """Despliega un menú para seleccionar el monitor a capturar."""
        monitores = self._detectar_monitores()
        if not monitores:
            return

        menu = QMenu(self)
        menu.setStyleSheet(_stylesheet_menu_monitores(temas.obtener_paleta_activa()))

        # Leer monitor actual de config
        cfg = cargar_config()
        monitor_actual = cfg.get("monitor_captura", 1)

        # Opciones individuales
        for mon in monitores:
            accion = QAction(mon["nombre"], self)
            accion.setCheckable(True)
            accion.setChecked(monitor_actual == mon["indice"])
            accion.triggered.connect(
                lambda checked, idx=mon["indice"]: self._seleccionar_monitor(idx)
            )
            menu.addAction(accion)

        # Separador + opción "Todos"
        if len(monitores) > 1:
            menu.addSeparator()
            accion_todos = QAction("⚠ Todos los monitores (panorámico)", self)
            accion_todos.setCheckable(True)
            accion_todos.setChecked(monitor_actual == -1)
            accion_todos.triggered.connect(
                lambda checked: self._seleccionar_monitor(-1)
            )
            menu.addAction(accion_todos)

        # Mostrar menú debajo del botón
        menu.exec_(self.btn_monitor.mapToGlobal(
            self.btn_monitor.rect().bottomLeft()
        ))

    def _seleccionar_monitor(self, indice: int):
        """Guarda la selección de monitor en config.json."""
        # Alerta si elige todos los monitores
        if indice == -1:
            resp = QMessageBox.warning(
                self, "⚠ Captura panorámica",
                "Capturar todos los monitores genera imágenes más grandes\n"
                "y puede sobrecargar el procesamiento del agente.\n\n"
                "¿Deseas continuar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return

        try:
            ruta_config = Path(__file__).parent / "config.json"
            with open(ruta_config, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["monitor_captura"] = indice
            with open(ruta_config, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            if indice == -1:
                nombre = "Todos los monitores"
            else:
                nombre = f"Monitor {indice}"
            self.senales.actualizar_ui.emit(f"🖥 Capturando: {nombre}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo guardar:\n{e}")

    def _abrir_configuraciones(self):
        """Abre el popup de configuraciones del agente."""
        popup = PopupConfiguraciones(self, gestor_chat=self.gestor_chat)
        popup.exec_()

    def _on_tray_click(self, motivo):
        if motivo == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def _cerrar_agente(self):
        if self.gestor_bitacora:
            self.gestor_bitacora.cerrar_jornada()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Agente LLM - El Egypcio",
            "El agente sigue corriendo en segundo plano.",
            QSystemTrayIcon.Information,
            2000
        )

    def resizeEvent(self, event):
        """Forzar que el contenedor interno se ajuste al ancho de la ventana."""
        super().resizeEvent(event)
        scroll_width = self._scroll.viewport().width()
        # Proteger contra ancho 0 durante la inicialización
        if scroll_width > 50:
            self._contenedor.setFixedWidth(scroll_width)

    def showEvent(self, event):
        """Forzar tamaño y layout correctos la primera vez que se muestra."""
        super().showEvent(event)
        if self._primera_muestra:
            self._primera_muestra = False
            # Forzar el tamaño deseado
            self.resize(400, 560)
            # Procesar eventos pendientes para que el viewport tenga ancho real
            QApplication.processEvents()
            # Ahora sí recalcular el ancho del contenedor
            scroll_width = self._scroll.viewport().width()
            if scroll_width > 50:
                self._contenedor.setFixedWidth(scroll_width)

    def es_pausado(self) -> bool:
        return self._pausado

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _separador(self):
        linea = QFrame()
        linea.setFrameShape(QFrame.HLine)
        linea.setFrameShadow(QFrame.Sunken)
        return linea


# ---------------------------------------------------------------------------
# Popup de gestión de proyectos
# ---------------------------------------------------------------------------
class PopupProyectos(QDialog):
    """
    Popup para crear, editar y cerrar proyectos del Gantt.
    Tres vistas: lista principal, formulario nuevo, formulario edición.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestión de Proyectos")
        self.setWindowIcon(_resolver_icono("ventana.ico"))
        self.setMinimumWidth(460)                # ← DIMENSIÓN: ancho mínimo popup proyectos
        self.setMinimumHeight(320)               # ← DIMENSIÓN: alto mínimo popup proyectos
        self.resize(480, 380)                    # ← DIMENSIÓN: tamaño inicial popup proyectos
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._layout = QVBoxLayout(self)
        self._mostrar_lista()
        self._aplicar_estilo()

    def _limpiar(self):
        """
        Vacía el layout principal destruyendo TODOS los widgets, incluyendo
        los que están dentro de sub-layouts (QHBoxLayout anidados, etc.).

        La versión anterior solo destruía widgets de primer nivel — los
        widgets dentro de sub-layouts quedaban huérfanos pero vivos en
        memoria, lo que causaba que referencias como `self.campo_temperatura`
        pudieran terminar apuntando a spinboxes fantasma al reabrir un
        formulario, generando bugs intermitentes de persistencia.
        """
        def _vaciar_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                elif item.layout():
                    _vaciar_layout(item.layout())
        _vaciar_layout(self._layout)

    def _aplicar_estilo(self):
        """Aplica el stylesheet del tema activo a este popup."""
        self.setStyleSheet(_stylesheet_popup_proyectos(temas.obtener_paleta_activa()))

    # ------------------------------------------------------------------
    # Vista 1 — Lista de proyectos
    # ------------------------------------------------------------------
    def _mostrar_lista(self):
        self._limpiar()

        # Título fuera del scroll (siempre visible arriba)
        titulo = QLabel("🗂 Proyectos activos")
        titulo.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._layout.addWidget(titulo)

        # Leer todos los proyectos con su índice real en config.json
        import json as _json
        ruta_cfg = Path(__file__).parent / "config.json"
        with open(ruta_cfg, encoding="utf-8") as _f:
            todos = _json.load(_f).get("proyectos", [])

        # Particionar y ordenar: activos primero, cerrados después
        activos  = [(i, p) for i, p in enumerate(todos) if p.get("estado") == "activo"]
        cerrados = [(i, p) for i, p in enumerate(todos) if p.get("estado") == "cerrado"]

        # Área scrollable para la lista de proyectos. Solo la lista hace
        # scroll; el título arriba y los botones de acción abajo se quedan
        # fijos para que siempre estén accesibles sin tener que scrollear.
        scroll = QScrollArea()
        scroll.setObjectName("scroll_proyectos")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)  # sin borde, integrado al popup

        contenedor_lista = QWidget()
        layout_lista = QVBoxLayout(contenedor_lista)
        layout_lista.setContentsMargins(0, 0, 0, 0)   # ← DIMENSIÓN: margen interno scroll lista proyectos
        layout_lista.setSpacing(4)                    # ← DIMENSIÓN: espacio vertical entre filas proyecto

        if not activos and not cerrados:
            lbl = QLabel("No hay proyectos aún.")
            lbl.setObjectName("subtitulo")
            layout_lista.addWidget(lbl)
        else:
            # Activos
            for idx_real, p in activos:
                layout_lista.addWidget(self._fila_proyecto(idx_real, p, activo=True))

            # Cerrados (si los hay)
            if cerrados:
                if activos:
                    # Separador visual entre activos y cerrados
                    sep = QLabel("— Cerrados —")
                    sep.setObjectName("subtitulo")
                    sep.setAlignment(Qt.AlignCenter)
                    layout_lista.addWidget(sep)
                for idx_real, p in cerrados:
                    layout_lista.addWidget(self._fila_proyecto(idx_real, p, activo=False))

        layout_lista.addStretch()
        scroll.setWidget(contenedor_lista)
        self._layout.addWidget(scroll, stretch=1)  # ocupa todo el espacio disponible

        # Botones inferiores fijos (fuera del scroll)
        btn_nuevo = QPushButton("+ Nuevo proyecto")
        btn_nuevo.setObjectName("btn_nuevo")
        btn_nuevo.clicked.connect(self._mostrar_formulario_nuevo)
        self._layout.addWidget(btn_nuevo)

        btn_migrar = QPushButton("🔄 Migrar bitácoras antiguas")
        btn_migrar.setToolTip(
            "Clasifica retroactivamente todas las bitácoras existentes\n"
            "y las vincula a los proyectos correspondientes."
        )
        btn_migrar.clicked.connect(self._ejecutar_migracion)
        self._layout.addWidget(btn_migrar)

        btn_cerrar_popup = QPushButton("Cerrar")
        btn_cerrar_popup.clicked.connect(self.accept)
        self._layout.addWidget(btn_cerrar_popup)

    def _fila_proyecto(self, idx_real: int, p: dict, activo: bool) -> QWidget:
        """
        Construye la fila visual para un proyecto.
        Si activo=True: emoji 📌, color normal, botón rosa "✖ Cerrar".
        Si activo=False: emoji 🔒, color atenuado, botón verde "✓ Activar".
        El botón Editar se mantiene en ambos casos.
        """
        fila = QHBoxLayout()
        emoji = "📌" if activo else "🔒"
        nombre = QLabel(f"{emoji} {p['nombre']}")
        nombre.setFont(QFont("Segoe UI", 9, QFont.Bold))
        if not activo:
            nombre.setObjectName("nombre_cerrado")

        kw_texto = (
            p.get("descripcion", "")
            or p.get("palabras_clave", "")
            or "(sin descripción)"
        )
        kw = QLabel(kw_texto[:50])
        kw.setObjectName("subtitulo_cerrado" if not activo else "subtitulo")

        btn_editar = QPushButton("✏️ Editar")
        btn_editar.setFixedWidth(80)   # ← DIMENSIÓN: ancho botón Editar
        btn_editar.clicked.connect(lambda _, idx=idx_real: self._mostrar_edicion(idx))

        if activo:
            btn_accion = QPushButton("✖ Cerrar")
            btn_accion.setObjectName("btn_cerrar_proyecto")
            btn_accion.clicked.connect(lambda _, idx=idx_real: self._cerrar_proyecto(idx))
        else:
            btn_accion = QPushButton("✓ Activar")
            btn_accion.setObjectName("btn_activar_proyecto")
            btn_accion.clicked.connect(lambda _, idx=idx_real: self._activar_proyecto(idx))
        btn_accion.setFixedWidth(80)   # ← DIMENSIÓN: ancho botón Cerrar/Activar

        col = QVBoxLayout()
        col.addWidget(nombre)
        col.addWidget(kw)

        fila.addLayout(col)
        fila.addStretch()
        fila.addWidget(btn_editar)
        fila.addWidget(btn_accion)

        contenedor = QWidget()
        contenedor.setLayout(fila)
        return contenedor

    # ------------------------------------------------------------------
    # Vista 2 — Formulario nuevo proyecto
    # ------------------------------------------------------------------
    def _mostrar_formulario_nuevo(self):
        self._limpiar()

        titulo = QLabel("+ Nuevo proyecto")
        titulo.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._layout.addWidget(titulo)

        # Título
        self._layout.addWidget(QLabel("Título del proyecto:"))
        self.campo_titulo = QLineEdit()
        self.campo_titulo.setPlaceholderText("Ej: Maestro Estudiantes")
        self._layout.addWidget(self.campo_titulo)

        # Descripción general
        self._layout.addWidget(QLabel("Descripción general:"))
        self.campo_descripcion = QTextEdit()
        self.campo_descripcion.setPlaceholderText(
            "Describe qué es este proyecto: contexto, fuentes de datos, "
            "stakeholders, herramientas principales..."
        )
        self.campo_descripcion.setMinimumHeight(80)
        self.campo_descripcion.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self.campo_descripcion)

        # Objetivos específicos
        self._layout.addWidget(QLabel("Objetivos específicos:"))
        self.campo_objetivos = QTextEdit()
        self.campo_objetivos.setPlaceholderText(
            "Lista las actividades concretas que cuentan como parte del "
            "proyecto. Ej: 'Construir query SQL en Athena para tabla X', "
            "'Validar resultados con DBeaver', 'Reunión con Pablo Rubilar'."
        )
        self.campo_objetivos.setMinimumHeight(80)
        self.campo_objetivos.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self.campo_objetivos)

        # Temperatura de clasificación
        fila_temp = QHBoxLayout()
        lbl_temp = QLabel("Temperatura de clasificación:")
        self.campo_temperatura = QDoubleSpinBox()
        self.campo_temperatura.setRange(0.0, 1.0)
        self.campo_temperatura.setSingleStep(0.1)
        self.campo_temperatura.setDecimals(1)
        self.campo_temperatura.setValue(0.2)
        self.campo_temperatura.setFixedWidth(80)
        fila_temp.addWidget(lbl_temp)
        fila_temp.addWidget(self.campo_temperatura)
        fila_temp.addStretch()
        self._layout.addLayout(fila_temp)

        lbl_hint = QLabel(
            "🎯 Mientras más específicos sean los objetivos, mejor la clasificación.\n"
            "🌡 Temperatura baja (0.0–0.2) → clasificación determinista.\n"
            "🌡 Temperatura alta (0.5+) → más variación, útil si el proyecto es transversal."
        )
        lbl_hint.setObjectName("subtitulo")
        lbl_hint.setWordWrap(True)
        self._layout.addWidget(lbl_hint)

        self._layout.addStretch()

        fila = QHBoxLayout()
        btn_guardar = QPushButton("✅ Crear proyecto")
        btn_guardar.clicked.connect(self._guardar_nuevo)
        btn_volver = QPushButton("← Volver")
        btn_volver.clicked.connect(self._mostrar_lista)
        fila.addWidget(btn_volver)
        fila.addWidget(btn_guardar)
        self._layout.addLayout(fila)

    def _guardar_nuevo(self):
        nombre = self.campo_titulo.text().strip()
        descripcion = self.campo_descripcion.toPlainText().strip()
        objetivos = self.campo_objetivos.toPlainText().strip()
        # interpretText() fuerza al spinbox a procesar el texto pendiente
        # antes de leer .value(). Previene perder cambios cuando el usuario
        # tipea un valor y presiona Guardar sin Enter ni cambiar foco.
        self.campo_temperatura.interpretText()
        temperatura = float(self.campo_temperatura.value())
        if not nombre:
            return
        agregar_proyecto(nombre, descripcion, objetivos, temperatura)
        # Crear archivo .md del proyecto en Obsidian
        try:
            crear_md_proyecto(nombre, descripcion, objetivos)
        except Exception as e:
            print(f"[Proyectos] Error creando .md: {e}")
        self._mostrar_lista()

    # ------------------------------------------------------------------
    # Vista 3 — Formulario edición proyecto
    # ------------------------------------------------------------------
    def _mostrar_edicion(self, indice: int):
        self._limpiar()
        import json as _json
        ruta_cfg = Path(__file__).parent / "config.json"
        with open(ruta_cfg, encoding="utf-8") as _f:
            config_raw = _json.load(_f)
        proyecto = config_raw["proyectos"][indice]

        # Migración silenciosa en pantalla: si no hay campo nuevo, usar legacy
        descripcion_inicial = proyecto.get("descripcion", "") or proyecto.get("palabras_clave", "")
        objetivos_inicial = proyecto.get("objetivos", "")
        temperatura_inicial = float(proyecto.get("temperatura", 0.2) or 0.2)
        temperatura_inicial = max(0.0, min(1.0, temperatura_inicial))

        titulo = QLabel(f"✏️ Editar proyecto")
        titulo.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._layout.addWidget(titulo)

        # Título
        self._layout.addWidget(QLabel("Título:"))
        self.campo_titulo = QLineEdit(proyecto.get("nombre", ""))
        self._layout.addWidget(self.campo_titulo)

        # Descripción general
        self._layout.addWidget(QLabel("Descripción general:"))
        self.campo_descripcion = QTextEdit()
        self.campo_descripcion.setPlainText(descripcion_inicial)
        self.campo_descripcion.setMinimumHeight(80)
        self.campo_descripcion.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self.campo_descripcion)

        # Objetivos específicos
        self._layout.addWidget(QLabel("Objetivos específicos:"))
        self.campo_objetivos = QTextEdit()
        self.campo_objetivos.setPlainText(objetivos_inicial)
        self.campo_objetivos.setMinimumHeight(80)
        self.campo_objetivos.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._layout.addWidget(self.campo_objetivos)

        # Temperatura
        fila_temp = QHBoxLayout()
        lbl_temp = QLabel("Temperatura de clasificación:")
        self.campo_temperatura = QDoubleSpinBox()
        self.campo_temperatura.setRange(0.0, 1.0)
        self.campo_temperatura.setSingleStep(0.1)
        self.campo_temperatura.setDecimals(1)
        self.campo_temperatura.setValue(temperatura_inicial)
        self.campo_temperatura.setFixedWidth(80)
        fila_temp.addWidget(lbl_temp)
        fila_temp.addWidget(self.campo_temperatura)
        fila_temp.addStretch()
        self._layout.addLayout(fila_temp)

        self._layout.addStretch()

        fila = QHBoxLayout()
        btn_volver  = QPushButton("← Volver")
        btn_volver.clicked.connect(self._mostrar_lista)
        btn_guardar = QPushButton("✅ Guardar")
        btn_guardar.clicked.connect(lambda: self._guardar_edicion(indice))
        fila.addWidget(btn_volver)
        fila.addWidget(btn_guardar)
        self._layout.addLayout(fila)

    def _guardar_edicion(self, indice: int):
        nombre = self.campo_titulo.text().strip()
        descripcion = self.campo_descripcion.toPlainText().strip()
        objetivos = self.campo_objetivos.toPlainText().strip()
        # interpretText() fuerza al spinbox a procesar el texto pendiente
        # antes de leer .value(). Previene perder cambios cuando el usuario
        # tipea un valor y presiona Guardar sin Enter ni cambiar foco.
        self.campo_temperatura.interpretText()
        temperatura = float(self.campo_temperatura.value())
        if not nombre:
            return
        editar_proyecto(indice, nombre, descripcion, objetivos, temperatura, "activo")
        self._mostrar_lista()

    def _cerrar_proyecto(self, indice: int):
        """
        Cierra un proyecto activo. Preserva todos los campos actuales y solo
        cambia el estado a 'cerrado'.
        """
        import json as _json
        ruta_cfg = Path(__file__).parent / "config.json"
        with open(ruta_cfg, encoding="utf-8") as _f:
            config_raw = _json.load(_f)
        proyecto = config_raw["proyectos"][indice]
        # Migración silenciosa: si el proyecto venía sin campos nuevos, los rellenamos
        descripcion = proyecto.get("descripcion", "") or proyecto.get("palabras_clave", "")
        objetivos = proyecto.get("objetivos", "")
        temperatura = float(proyecto.get("temperatura", 0.2) or 0.2)
        editar_proyecto(indice, proyecto.get("nombre", ""),
                        descripcion, objetivos, temperatura,
                        "cerrado")
        self._mostrar_lista()

    def _activar_proyecto(self, indice: int):
        """
        Reactiva un proyecto cerrado. Delega en gantt.editar_proyecto, que se
        encarga de limpiar `fin` cuando el nuevo estado es "activo".
        """
        import json as _json
        ruta_cfg = Path(__file__).parent / "config.json"
        with open(ruta_cfg, encoding="utf-8") as _f:
            config_raw = _json.load(_f)
        proyecto = config_raw["proyectos"][indice]
        descripcion = proyecto.get("descripcion", "") or proyecto.get("palabras_clave", "")
        objetivos = proyecto.get("objetivos", "")
        temperatura = float(proyecto.get("temperatura", 0.2) or 0.2)
        editar_proyecto(indice, proyecto.get("nombre", ""),
                        descripcion, objetivos, temperatura,
                        "activo")
        self._mostrar_lista()

    def _ejecutar_migracion(self):
        """Ejecuta la migración retroactiva con feedback visual."""
        respuesta = QMessageBox.question(
            self,
            "Migrar bitácoras",
            "Esto leerá todas las bitácoras existentes y las clasificará\n"
            "contra los proyectos activos usando Claude.\n\n"
            "Puede tomar varios minutos según la cantidad de archivos.\n\n"
            "¿Deseas continuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if respuesta != QMessageBox.Yes:
            return

        # Ejecutar migración en hilo separado para no congelar la UI
        import threading
        self._resultado_migracion = None

        def _worker():
            try:
                stats = migrar_bitacoras_antiguas()
                msg = (
                    f"Migración completada ✅\n\n"
                    f"Archivos procesados: {stats.get('archivos_procesados', 0)}\n"
                    f"Entradas analizadas: {stats.get('entradas_procesadas', 0)}\n"
                    f"Matches encontrados: {stats.get('matches', 0)}\n\n"
                )
                por_proyecto = stats.get("por_proyecto", {})
                if por_proyecto:
                    msg += "Por proyecto:\n"
                    for nombre, cant in por_proyecto.items():
                        msg += f"  • {nombre}: {cant} entradas\n"
                self._resultado_migracion = ("ok", msg)
            except Exception as e:
                self._resultado_migracion = ("error", f"Error en migración:\n{e}")

        threading.Thread(target=_worker, daemon=True).start()

        # Polling cada 1s desde el hilo principal
        timer = QTimer(self)
        timer.setInterval(1000)
        def _check():
            if self._resultado_migracion is not None:
                timer.stop()
                tipo, msg = self._resultado_migracion
                if tipo == "ok":
                    QMessageBox.information(self, "Migración completada", msg)
                else:
                    QMessageBox.warning(self, "Error", msg)
        timer.timeout.connect(_check)
        timer.start()

        QMessageBox.information(
            self, "Migración en curso",
            "La migración se está ejecutando en segundo plano.\n"
            "Recibirás una notificación cuando termine."
        )

    @staticmethod
    def _abrir_obsidian_archivo(archivo: Path):
        """Abre el vault en Obsidian (o la carpeta del archivo si no se puede)."""
        config = cargar_config()
        ruta_1 = config.get("ruta_obsidian_1", "")
        ruta_2 = config.get("ruta_obsidian_2", "")

        if (ruta_1 and Path(ruta_1).exists()) or (ruta_2 and Path(ruta_2).exists()):
            # Abrir el vault por nombre vía URI (no por ruta de carpeta, que
            # Obsidian podría malinterpretar como un vault nuevo).
            os.startfile(uri_obsidian())
        else:
            subprocess.Popen(["explorer", str(archivo.parent)], shell=True)


# ---------------------------------------------------------------------------
# Popup de selección de Gantt
# ---------------------------------------------------------------------------
class PopupGantt(QDialog):
    """
    Popup para elegir qué Gantt abrir: el global o el de un proyecto específico.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Abrir Gantt")
        self.setWindowIcon(_resolver_icono("ventana.ico"))
        self.setMinimumWidth(380)                # ← DIMENSIÓN: ancho mínimo popup Gantt
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._aplicar_estilo()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        titulo = QLabel("📊 ¿Qué Gantt deseas abrir?")
        titulo.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(titulo)

        # Botón Gantt global
        btn_global = QPushButton("🌐 Abrir Gantt global (todos los proyectos)")
        btn_global.setObjectName("btn_global")
        btn_global.setMinimumHeight(40)         # ← DIMENSIÓN: alto botón Gantt global
        btn_global.clicked.connect(self._abrir_global)
        layout.addWidget(btn_global)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # Selector de proyecto
        lbl_sel = QLabel("O selecciona un proyecto específico:")
        layout.addWidget(lbl_sel)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(32)         # ← DIMENSIÓN: alto combobox proyectos
        proyectos = listar_proyectos_con_md()

        if not proyectos:
            self.combo.addItem("(No hay proyectos con archivo .md)")
            self.combo.setEnabled(False)
        else:
            for nombre, _ in proyectos:
                self.combo.addItem(nombre)

        layout.addWidget(self.combo)

        btn_proyecto = QPushButton("📂 Abrir proyecto seleccionado")
        btn_proyecto.setMinimumHeight(40)
        btn_proyecto.setEnabled(bool(proyectos))
        btn_proyecto.clicked.connect(self._abrir_proyecto)
        layout.addWidget(btn_proyecto)

        layout.addStretch()

        btn_cerrar = QPushButton("Cancelar")
        btn_cerrar.clicked.connect(self.reject)
        layout.addWidget(btn_cerrar)

    def _aplicar_estilo(self):
        """Aplica el stylesheet del tema activo a este popup."""
        self.setStyleSheet(_stylesheet_popup_gantt(temas.obtener_paleta_activa()))

    def _abrir_global(self):
        """Abre el archivo gantt_proyectos.md global en Obsidian."""
        archivo = ruta_proyectos() / "gantt_proyectos.md"
        if not archivo.exists():
            generar_mermaid()
        # Abre el archivo específico vía URI (vault real + ruta relativa)
        self._abrir_archivo_en_obsidian("proyectos/gantt_proyectos", archivo)
        self.accept()

    def _abrir_proyecto(self):
        """Abre el .md del proyecto seleccionado en Obsidian."""
        nombre = self.combo.currentText()
        if not nombre or "(No hay" in nombre:
            return
        ruta = ruta_md_proyecto(nombre)
        if not ruta.exists():
            crear_md_proyecto(nombre)
        # El nombre de archivo del MOC (sin .md) relativo a proyectos/
        nombre_archivo = ruta.stem
        self._abrir_archivo_en_obsidian(f"proyectos/{nombre_archivo}", ruta)
        self.accept()

    def _abrir_archivo_en_obsidian(self, ruta_relativa_vault: str, archivo_fallback: Path):
        """
        Abre un archivo específico en Obsidian vía URI obsidian://, usando el
        nombre real del vault. Si Obsidian no está disponible, abre la carpeta
        contenedora en el Explorador como fallback.

        Args:
            ruta_relativa_vault: ruta del archivo relativa a la raíz del vault,
                con "/" y SIN extensión (ej: "proyectos/gantt_proyectos").
            archivo_fallback: Path real del archivo, para el fallback a Explorer.
        """
        config = cargar_config()
        ruta_1 = config.get("ruta_obsidian_1", "")
        ruta_2 = config.get("ruta_obsidian_2", "")

        if (ruta_1 and Path(ruta_1).exists()) or (ruta_2 and Path(ruta_2).exists()):
            os.startfile(uri_obsidian(ruta_relativa_vault))
        else:
            subprocess.Popen(["explorer", str(archivo_fallback.parent)], shell=True)

    def _abrir_en_obsidian(self, ruta_base: Path):
        """
        Abre el vault de Obsidian (sin archivo específico). El usuario navega
        desde ahí. Se mantiene como fallback para usos genéricos.
        """
        config = cargar_config()
        ruta_1 = config.get("ruta_obsidian_1", "")
        ruta_2 = config.get("ruta_obsidian_2", "")

        if (ruta_1 and Path(ruta_1).exists()) or (ruta_2 and Path(ruta_2).exists()):
            # Abrir el vault por nombre vía URI, no por ruta de carpeta
            os.startfile(uri_obsidian())
        else:
            subprocess.Popen(["explorer", str(ruta_base)], shell=True)


# ---------------------------------------------------------------------------
# Popup de Configuraciones
# ---------------------------------------------------------------------------
class PopupConfiguraciones(QDialog):
    """
    Configuraciones del agente:
    - Lista blanca de aplicaciones laborales
    - Lista negra (siempre ignoradas)
    - Palabras clave laborales en browser
    - Días de contexto del chat
    - Días para alerta de inactividad
    - Prompt del agente (instrucciones permanentes para el LLM)

    Los cambios se aplican en caliente (excepto alertas de inactividad,
    que aplican en el próximo arranque del agente).
    """

    def __init__(self, parent=None, gestor_chat=None):
        super().__init__(parent)
        self.gestor_chat = gestor_chat
        self.setWindowTitle("⚙ Configuraciones")
        self.setWindowIcon(_resolver_icono("ventana.ico"))
        self.setMinimumWidth(520)                # ← DIMENSIÓN: ancho mínimo popup configuraciones
        self.setMinimumHeight(560)               # ← DIMENSIÓN: alto mínimo popup configuraciones
        self.resize(560, 640)                    # ← DIMENSIÓN: tamaño inicial popup configuraciones
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # Cargar config actual
        self._ruta_config = Path(__file__).parent / "config.json"
        with open(self._ruta_config, encoding="utf-8") as f:
            self._config_actual = json.load(f)

        self._construir_ui()
        self._aplicar_estilo()
        self._poblar_campos()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _construir_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # --- Scroll para el contenido ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # Título
        titulo = QLabel("⚙ Configuraciones del agente")
        titulo.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(titulo)

        subt = QLabel(
            "Los cambios en listas, días de contexto y prompt del agente se aplican inmediatamente.\n"
            "El umbral de alerta de inactividad aplica en el próximo arranque."
        )
        subt.setObjectName("hint")
        subt.setWordWrap(True)
        layout.addWidget(subt)

        # --- Sección: Lista blanca de procesos (.exe) ---
        layout.addWidget(self._titulo_seccion("✅ Lista blanca de procesos (.exe)"))
        layout.addWidget(self._hint(
            "Apps de escritorio que SÍ se registran. Una por línea.\n"
            "Ejemplos: EXCEL.EXE, dbeaver.exe, Code.exe, Obsidian.exe"
        ))
        self.txt_blanca = QTextEdit()
        self.txt_blanca.setMinimumHeight(110)    # ← DIMENSIÓN: alto campo lista blanca
        self.txt_blanca.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_blanca)

        # --- Sección: Lista negra de procesos (.exe) ---
        layout.addWidget(self._titulo_seccion("🚫 Lista negra de procesos (.exe)"))
        layout.addWidget(self._hint(
            "Apps de escritorio que NUNCA se registran. Una por línea.\n"
            "Ejemplos: Spotify.exe, WhatsApp.exe, Discord.exe"
        ))
        self.txt_negra = QTextEdit()
        self.txt_negra.setMinimumHeight(90)      # ← DIMENSIÓN: alto campo lista negra
        self.txt_negra.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_negra)

        # --- Sección: Palabras clave laborales en browser/UWP ---
        layout.addWidget(self._titulo_seccion("🌐 Palabras clave laborales en browser/UWP"))
        layout.addWidget(self._hint(
            "Si el título de un browser o app moderna (Outlook nuevo, Teams nuevo) "
            "contiene alguna de estas palabras, se registra. Una por línea."
        ))
        self.txt_browser = QTextEdit()
        self.txt_browser.setMinimumHeight(90)    # ← DIMENSIÓN: alto campo palabras browser
        self.txt_browser.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_browser)

        # --- Sección: Keywords bloqueadas en browser/UWP ---
        layout.addWidget(self._titulo_seccion("🚷 Keywords bloqueadas en browser/UWP"))
        layout.addWidget(self._hint(
            "Si el título de un browser/UWP contiene alguna de estas palabras, "
            "se ignora aunque haya keywords laborales. Una por línea.\n"
            "Ejemplos: youtube, netflix, spotify"
        ))
        self.txt_browser_bloqueadas = QTextEdit()
        self.txt_browser_bloqueadas.setMinimumHeight(90)  # ← DIMENSIÓN: alto campo keywords bloqueadas
        self.txt_browser_bloqueadas.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_browser_bloqueadas)

        # --- Sección: Personas conocidas ---
        layout.addWidget(self._titulo_seccion("👥 Personas conocidas"))
        layout.addWidget(self._hint(
            "Nombres que el agente reconoce en las bitácoras del día.\n"
            "Una persona por línea, formato: 'Nombre Apellido'.\n"
            "Ejemplos: Pablo Rubilar, Juan Nahuelpan"
        ))
        self.txt_personas = QTextEdit()
        self.txt_personas.setMinimumHeight(90)   # ← DIMENSIÓN: alto campo personas
        self.txt_personas.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_personas)

        # --- Sección: Días de contexto del chat ---
        layout.addWidget(self._titulo_seccion("💬 Días de contexto del chat"))
        layout.addWidget(self._hint(
            "Cuántos días atrás de bitácoras lee el chat al consultar."
        ))
        self.spin_contexto = QSpinBox()
        self.spin_contexto.setRange(1, 30)
        self.spin_contexto.setSuffix(" días")
        self.spin_contexto.setMinimumHeight(30)
        layout.addWidget(self.spin_contexto)

        # --- Sección: Alerta inactividad ---
        layout.addWidget(self._titulo_seccion("⚠ Alerta de inactividad"))
        layout.addWidget(self._hint(
            "Si un proyecto no tiene actividad por más de N días,\n"
            "se mostrará una alerta al iniciar el agente."
        ))
        self.spin_alerta = QSpinBox()
        self.spin_alerta.setRange(1, 30)
        self.spin_alerta.setSuffix(" días")
        self.spin_alerta.setMinimumHeight(30)
        layout.addWidget(self.spin_alerta)

        # --- Sección: Prompt del agente ---
        layout.addWidget(self._titulo_seccion("🤖 Prompt del agente"))
        layout.addWidget(self._hint(
            "Instrucciones permanentes que recibe el LLM en cada conversación.\n"
            "Variables disponibles (opcional, se sustituyen automáticamente):\n"
            "  • {nombre_usuario} → tu nombre del config (actualmente: "
            + self._config_actual.get("nombre_usuario", "Diego") + ")\n"
            "  • {dias_contexto} → días de bitácoras configurados\n"
            "Si lo dejas vacío o lo restauras, se usa el prompt por defecto."
        ))
        self.txt_system_prompt = QTextEdit()
        self.txt_system_prompt.setMinimumHeight(220)   # ← DIMENSIÓN: alto inicial textarea prompt
        self.txt_system_prompt.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_system_prompt)

        # Botón restaurar default (debajo del textarea, alineado a la derecha)
        fila_btn_prompt = QHBoxLayout()
        fila_btn_prompt.addStretch()
        self.btn_restaurar_prompt = QPushButton("↺ Restaurar default")
        self.btn_restaurar_prompt.setToolTip(
            "Reemplaza el contenido del campo con el prompt por defecto.\n"
            "Recuerda presionar 'Guardar cambios' para que el reemplazo se persista."
        )
        self.btn_restaurar_prompt.clicked.connect(self._restaurar_prompt_default)
        fila_btn_prompt.addWidget(self.btn_restaurar_prompt)
        layout.addLayout(fila_btn_prompt)

        # --- Sección: Prompt de clasificación de proyectos ---
        layout.addWidget(self._titulo_seccion("🎯 Prompt de clasificación de proyectos"))
        placeholders_listado = ", ".join(
            "{" + ph + "}" for ph in PLACEHOLDERS_CLASIFICACION
        )
        layout.addWidget(self._hint(
            "Plantilla del prompt que el LLM recibe para decidir a qué proyecto\n"
            "pertenece cada actividad detectada.\n\n"
            "Placeholders OBLIGATORIOS (deben aparecer textualmente):\n"
            "  • {titulo_ventana}        → título de la ventana detectada\n"
            "  • {descripcion_actividad} → resumen de la actividad\n"
            "  • {lista_proyectos}       → bloque con descripción y objetivos de cada proyecto\n"
            "  • {lista_nombres}         → lista de nombres válidos como respuesta\n\n"
            "Si falta cualquier placeholder, el guardado será rechazado.\n"
            "Si el campo queda vacío, se usa la plantilla por defecto."
        ))
        self.txt_prompt_clasificacion = QTextEdit()
        self.txt_prompt_clasificacion.setMinimumHeight(220)
        self.txt_prompt_clasificacion.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_prompt_clasificacion)

        # Botón restaurar default para el prompt de clasificación
        fila_btn_clas = QHBoxLayout()
        fila_btn_clas.addStretch()
        self.btn_restaurar_clasificacion = QPushButton("↺ Restaurar default")
        self.btn_restaurar_clasificacion.setToolTip(
            "Reemplaza el contenido del campo con la plantilla por defecto.\n"
            "Recuerda presionar 'Guardar cambios' para persistir."
        )
        self.btn_restaurar_clasificacion.clicked.connect(
            self._restaurar_prompt_clasificacion_default
        )
        fila_btn_clas.addWidget(self.btn_restaurar_clasificacion)
        layout.addLayout(fila_btn_clas)

        # --- Sección: Prompt de análisis de imágenes (actividad) ---
        layout.addWidget(self._titulo_seccion("🖼️ Prompt de análisis de imágenes — Actividad"))
        layout.addWidget(self._hint(
            "Plantilla del prompt que el LLM recibe al analizar una captura de\n"
            "actividad normal (no reunión). Debe pedir un JSON con los campos\n"
            "actividad, categoria, herramienta y urls.\n\n"
            "Placeholder OBLIGATORIO:\n"
            "  • {titulo_ventana}  → título de la ventana detectada\n\n"
            "Si falta, el guardado será rechazado. Si el campo queda vacío,\n"
            "se usa la plantilla por defecto."
        ))
        self.txt_prompt_img_actividad = QTextEdit()
        self.txt_prompt_img_actividad.setMinimumHeight(200)
        self.txt_prompt_img_actividad.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_prompt_img_actividad)

        fila_btn_img_act = QHBoxLayout()
        fila_btn_img_act.addStretch()
        self.btn_restaurar_img_actividad = QPushButton("↺ Restaurar default")
        self.btn_restaurar_img_actividad.setToolTip(
            "Reemplaza el contenido con la plantilla por defecto.\n"
            "Recuerda presionar 'Guardar cambios' para persistir."
        )
        self.btn_restaurar_img_actividad.clicked.connect(
            self._restaurar_prompt_img_actividad_default
        )
        fila_btn_img_act.addWidget(self.btn_restaurar_img_actividad)
        layout.addLayout(fila_btn_img_act)

        # --- Sección: Prompt de análisis de imágenes (reunión) ---
        layout.addWidget(self._titulo_seccion("🖼️ Prompt de análisis de imágenes — Reunión"))
        layout.addWidget(self._hint(
            "Plantilla del prompt que el LLM recibe al analizar una captura\n"
            "durante una reunión. Debe detectar si se proyecta contenido y pedir\n"
            "un JSON con hay_proyeccion, descripcion, tipo_contenido y urls.\n\n"
            "Placeholder OBLIGATORIO:\n"
            "  • {titulo_ventana}  → título de la ventana de la reunión\n\n"
            "Si falta, el guardado será rechazado. Si el campo queda vacío,\n"
            "se usa la plantilla por defecto."
        ))
        self.txt_prompt_img_reunion = QTextEdit()
        self.txt_prompt_img_reunion.setMinimumHeight(200)
        self.txt_prompt_img_reunion.setFont(QFont("Consolas", 9))
        layout.addWidget(self.txt_prompt_img_reunion)

        fila_btn_img_reu = QHBoxLayout()
        fila_btn_img_reu.addStretch()
        self.btn_restaurar_img_reunion = QPushButton("↺ Restaurar default")
        self.btn_restaurar_img_reunion.setToolTip(
            "Reemplaza el contenido con la plantilla por defecto.\n"
            "Recuerda presionar 'Guardar cambios' para persistir."
        )
        self.btn_restaurar_img_reunion.clicked.connect(
            self._restaurar_prompt_img_reunion_default
        )
        fila_btn_img_reu.addWidget(self.btn_restaurar_img_reunion)
        layout.addLayout(fila_btn_img_reu)

        # --- Sección: Modelo de IA ---
        layout.addWidget(self._titulo_seccion("🤖 Modelo de IA"))

        # Etiqueta solo-lectura del proveedor activo
        proveedor_activo = self._config_actual.get("ia_proveedor", "claude")
        info_prov = PROVEEDORES.get(proveedor_activo, {"nombre": proveedor_activo, "icono": "•"})
        self.lbl_proveedor = QLabel(
            f"Proveedor activo: {info_prov['icono']} {info_prov['nombre']}"
        )
        self.lbl_proveedor.setObjectName("hint")
        layout.addWidget(self.lbl_proveedor)

        layout.addWidget(self._hint(
            "Selecciona el modelo a usar. El cambio se aplica en esta misma sesión.\n"
            "Para cambiar de proveedor, cierra y reinicia el agente."
        ))
        self.combo_modelo = QComboBox()
        self.combo_modelo.setMinimumHeight(30)
        modelos_disp = MODELOS_DISPONIBLES.get(proveedor_activo, [])
        self.combo_modelo.addItems(modelos_disp)
        layout.addWidget(self.combo_modelo)

        # --- Sección: FinOps (Consumo de API) ---
        layout.addWidget(self._titulo_seccion("📊 FinOps - Consumo de API"))
        layout.addWidget(self._hint(
            "Monitoreo de tokens y costo de cada llamada al LLM. "
            "Solo el chat del agente NO se registra dos veces (su uso "
            "ya se ve en chat_usuario)."
        ))

        # Contenedor del módulo: lo cargamos a través de _construir_modulo_finops
        # para poder refrescarlo cuando se presione el botón de refrescar.
        self._contenedor_finops = QWidget()
        self._contenedor_finops.setObjectName("contenedor_finops")
        self._layout_finops = QVBoxLayout(self._contenedor_finops)
        self._layout_finops.setContentsMargins(0, 0, 0, 0)
        self._layout_finops.setSpacing(8)
        self._construir_modulo_finops()
        layout.addWidget(self._contenedor_finops)

        # --- Sección: Tema visual (skins) ---
        layout.addWidget(self._titulo_seccion("🎨 Tema visual"))
        layout.addWidget(self._hint(
            "Esquema de colores de la aplicación. "
            "Selecciona uno y presiona 'Vista previa' para verlo "
            "aplicado en vivo. El cambio se persiste al guardar."
        ))

        # Combo de temas: lista temas.IDS_VALIDOS con emoji + nombre + descripción
        self.combo_tema = QComboBox()
        self.combo_tema.setMinimumHeight(30)
        for t in temas.listar_temas():
            self.combo_tema.addItem(
                f"{t['emoji']}  {t['nombre']} — {t['descripcion']}",
                userData=t["id"],
            )
        layout.addWidget(self.combo_tema)

        # Botón de vista previa
        fila_btn_tema = QHBoxLayout()
        fila_btn_tema.addStretch()
        self.btn_preview_tema = QPushButton("👁 Vista previa")
        self.btn_preview_tema.setObjectName("btn_preview_tema")
        self.btn_preview_tema.setToolTip(
            "Aplica el tema seleccionado a la ventana principal y a este "
            "popup, sin persistir. Si cancelas, vuelve al tema actual."
        )
        self.btn_preview_tema.clicked.connect(self._previsualizar_tema)
        fila_btn_tema.addWidget(self.btn_preview_tema)
        layout.addLayout(fila_btn_tema)

        layout.addStretch()
        scroll.setWidget(contenedor)
        layout_principal.addWidget(scroll)

        # --- Botones inferiores (fuera del scroll) ---
        # QFrame en lugar de QWidget para que respete background-color del CSS
        barra_botones = QFrame()
        barra_botones.setObjectName("barra_inferior")
        barra_botones.setAttribute(Qt.WA_StyledBackground, True)
        fila = QHBoxLayout(barra_botones)
        fila.setContentsMargins(18, 10, 18, 10)
        fila.setSpacing(10)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("✅ Guardar cambios")
        btn_guardar.setObjectName("btn_guardar")
        btn_guardar.clicked.connect(self._guardar)
        fila.addStretch()
        fila.addWidget(btn_cancelar)
        fila.addWidget(btn_guardar)

        layout_principal.addWidget(barra_botones)

    def _titulo_seccion(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        lbl.setObjectName("titulo_seccion")
        return lbl

    def _hint(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setObjectName("hint")
        lbl.setWordWrap(True)
        return lbl

    # ------------------------------------------------------------------
    # Estilo
    # ------------------------------------------------------------------
    def _aplicar_estilo(self):
        """Aplica el stylesheet del tema activo a este popup."""
        self.setStyleSheet(_stylesheet_popup_configuraciones(temas.obtener_paleta_activa()))

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------
    def _poblar_campos(self):
        """Llena los campos con los valores actuales de config.json."""
        cfg = self._config_actual
        # Listas de procesos (.exe) — preservan mayúsculas/minúsculas tal como
        # están en el archivo (los nombres de procesos en Windows son
        # case-insensitive en la práctica, pero conservamos el formato original).
        self.txt_blanca.setPlainText("\n".join(cfg.get("lista_blanca_procesos", [])))
        self.txt_negra.setPlainText("\n".join(cfg.get("lista_negra_procesos", [])))
        # Keywords de browser/UWP — siempre lowercase
        self.txt_browser.setPlainText("\n".join(cfg.get("palabras_clave_laborales_browser", [])))
        self.txt_browser_bloqueadas.setPlainText("\n".join(cfg.get("keywords_bloqueadas_browser", [])))
        # Personas conocidas — preserva mayúsculas (formato "Nombre Apellido")
        self.txt_personas.setPlainText("\n".join(cfg.get("personas_conocidas", [])))
        self.spin_contexto.setValue(cfg.get("dias_contexto_chat", 7))
        self.spin_alerta.setValue(cfg.get("alertas", {}).get("inactividad_dias", 3))

        # System prompt: si está vacío en config, mostrar el default como punto
        # de partida editable. Si tiene contenido, mostrar lo guardado.
        prompt_guardado = (cfg.get("system_prompt") or "").strip()
        self.txt_system_prompt.setPlainText(
            prompt_guardado if prompt_guardado else SYSTEM_PROMPT
        )

        # Prompt de clasificación: mismo patrón. Si está vacío en config,
        # se muestra el default como punto de partida editable.
        prompt_clas_guardado = (cfg.get("prompt_clasificacion") or "").strip()
        self.txt_prompt_clasificacion.setPlainText(
            prompt_clas_guardado if prompt_clas_guardado else PROMPT_CLASIFICACION_DEFAULT
        )

        # Prompts de imagen (actividad y reunión): mismo patrón.
        prompt_img_act_guardado = (cfg.get("prompt_imagen_actividad") or "").strip()
        self.txt_prompt_img_actividad.setPlainText(
            prompt_img_act_guardado if prompt_img_act_guardado
            else PROMPT_IMAGEN_ACTIVIDAD_DEFAULT
        )
        prompt_img_reu_guardado = (cfg.get("prompt_imagen_reunion") or "").strip()
        self.txt_prompt_img_reunion.setPlainText(
            prompt_img_reu_guardado if prompt_img_reu_guardado
            else PROMPT_IMAGEN_REUNION_DEFAULT
        )

        # Modelo de IA: seleccionar el modelo guardado para el proveedor activo
        proveedor_activo = cfg.get("ia_proveedor", "claude")
        modelo_default = MODELOS_PRINCIPALES.get(proveedor_activo, "")
        modelo_actual = cfg.get("ia_modelos", {}).get(proveedor_activo, modelo_default)
        idx = self.combo_modelo.findText(modelo_actual)
        if idx >= 0:
            self.combo_modelo.setCurrentIndex(idx)
        elif self.combo_modelo.count() > 0:
            # Si el modelo guardado no está en la lista, dejar el primero seleccionado
            self.combo_modelo.setCurrentIndex(0)

        # Tema visual: seleccionar el actual en el combo
        tema_actual = cfg.get("tema_visual", temas.ID_DEFAULT)
        if tema_actual not in temas.IDS_VALIDOS:
            tema_actual = temas.ID_DEFAULT
        for i in range(self.combo_tema.count()):
            if self.combo_tema.itemData(i) == tema_actual:
                self.combo_tema.setCurrentIndex(i)
                break

    def _restaurar_prompt_default(self):
        """
        Reemplaza el contenido del textarea con el SYSTEM_PROMPT por defecto.
        Solo afecta el textarea — el cambio recién se persiste cuando el
        usuario presiona "Guardar cambios".
        """
        self.txt_system_prompt.setPlainText(SYSTEM_PROMPT)
        QMessageBox.information(
            self,
            "Prompt restaurado",
            "Se cargó el prompt por defecto en el campo.\n"
            "Presiona 'Guardar cambios' para aplicarlo."
        )

    def _restaurar_prompt_clasificacion_default(self):
        """
        Reemplaza el contenido del textarea de clasificación con el template
        por defecto. Solo afecta el textarea — el cambio recién se persiste
        cuando el usuario presiona "Guardar cambios".
        """
        self.txt_prompt_clasificacion.setPlainText(PROMPT_CLASIFICACION_DEFAULT)
        QMessageBox.information(
            self,
            "Plantilla restaurada",
            "Se cargó la plantilla por defecto en el campo.\n"
            "Presiona 'Guardar cambios' para aplicarla."
        )

    def _restaurar_prompt_img_actividad_default(self):
        """Restaura el prompt de imagen (actividad) al default en el textarea."""
        self.txt_prompt_img_actividad.setPlainText(PROMPT_IMAGEN_ACTIVIDAD_DEFAULT)
        QMessageBox.information(
            self,
            "Plantilla restaurada",
            "Se cargó la plantilla de actividad por defecto en el campo.\n"
            "Presiona 'Guardar cambios' para aplicarla."
        )

    def _restaurar_prompt_img_reunion_default(self):
        """Restaura el prompt de imagen (reunión) al default en el textarea."""
        self.txt_prompt_img_reunion.setPlainText(PROMPT_IMAGEN_REUNION_DEFAULT)
        QMessageBox.information(
            self,
            "Plantilla restaurada",
            "Se cargó la plantilla de reunión por defecto en el campo.\n"
            "Presiona 'Guardar cambios' para aplicarla."
        )

    # ------------------------------------------------------------------
    # Selector de tema visual (skins)
    # ------------------------------------------------------------------
    def _previsualizar_tema(self):
        """
        Aplica el tema seleccionado en el combo a:
        - Este popup (en vivo)
        - La ventana principal del agente (en vivo)

        IMPORTANTE: este método NO persiste el cambio definitivamente. El
        config.json se sobrescribe TEMPORALMENTE para que obtener_paleta_activa()
        devuelva el nuevo tema; si el usuario presiona 'Cancelar', el override
        de reject() restaura el tema original.

        SOBRE EL RENDER:
        Los widgets visualmente "destacados" del módulo FinOps (tarjetas y
        gráfico) usan QFrame con WA_StyledBackground, lo que garantiza que
        respeten el `background-color` del stylesheet incluso al ser
        reconstruidos dinámicamente. Por eso aquí basta con:
        1. Aplicar el stylesheet nuevo.
        2. Reconstruir el módulo FinOps para que tome los nuevos colores.
        """
        tema_id = self.combo_tema.currentData()
        if not tema_id:
            return

        # 1. Persistir TEMPORALMENTE en config para que obtener_paleta_activa()
        #    devuelva el nuevo tema cuando se llame a _aplicar_estilo().
        #    Backup del tema original en una variable de instancia, para
        #    restaurarlo si el usuario presiona Cancelar (ver reject()).
        try:
            ruta_cfg = Path(__file__).parent / "config.json"
            import json as _json
            with open(ruta_cfg, encoding="utf-8") as f:
                cfg_actual = _json.load(f)
            if not hasattr(self, "_tema_original"):
                self._tema_original = cfg_actual.get("tema_visual", temas.ID_DEFAULT)
            cfg_actual["tema_visual"] = tema_id
            with open(ruta_cfg, "w", encoding="utf-8") as f:
                _json.dump(cfg_actual, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo previsualizar: {e}")
            return

        # 2. Aplicar el stylesheet del tema nuevo al popup.
        self._aplicar_estilo()

        # 3. Reconstruir el módulo FinOps con los nuevos colores. Sus widgets
        #    QFrame con WA_StyledBackground respetan el stylesheet correctamente.
        try:
            self._construir_modulo_finops()
        except Exception:
            pass  # si falla, no afecta el preview

        # 4. Aplicar a la ventana principal del agente (si está accesible).
        widget_parent = self.parent()
        while widget_parent is not None:
            if hasattr(widget_parent, "_aplicar_estilo"):
                try:
                    widget_parent._aplicar_estilo()
                except Exception:
                    pass
                break
            widget_parent = widget_parent.parent()

    def reject(self):
        """
        Override de reject() para restaurar el tema original si el usuario
        cancela tras haber hecho preview de un tema distinto.
        """
        if hasattr(self, "_tema_original"):
            try:
                ruta_cfg = Path(__file__).parent / "config.json"
                import json as _json
                with open(ruta_cfg, encoding="utf-8") as f:
                    cfg = _json.load(f)
                if cfg.get("tema_visual") != self._tema_original:
                    cfg["tema_visual"] = self._tema_original
                    with open(ruta_cfg, "w", encoding="utf-8") as f:
                        _json.dump(cfg, f, ensure_ascii=False, indent=2)
                    # Re-aplicar tema original a ventana principal
                    widget_parent = self.parent()
                    while widget_parent is not None:
                        if hasattr(widget_parent, "_aplicar_estilo"):
                            try:
                                widget_parent._aplicar_estilo()
                            except Exception:
                                pass
                            break
                        widget_parent = widget_parent.parent()
            except Exception:
                pass
        super().reject()

    # ------------------------------------------------------------------
    # Módulo FinOps: muestra consumo de API (tokens, costo, desglose)
    # ------------------------------------------------------------------
    def _construir_modulo_finops(self):
        """
        Construye dinámicamente el contenido del módulo FinOps dentro de
        self._contenedor_finops. Se puede llamar varias veces para refrescar.

        El módulo se adapta al ancho del popup (no fuerza scroll horizontal).
        """
        # Limpiar contenido previo
        while self._layout_finops.count():
            item = self._layout_finops.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Cargar datos
        try:
            import finops
            r_dia = finops.resumen_dia()
            r_mes = finops.resumen_mes()
            historico = finops.historico_ultimos_dias(5)
            info_precios = finops.info_precios()
        except Exception as e:
            err = QLabel(f"⚠ Error cargando datos FinOps: {e}")
            err.setObjectName("subtitulo")
            self._layout_finops.addWidget(err)
            return

        # === Fila de tarjetas: Hoy / Mes ===
        fila_tarjetas = QHBoxLayout()
        fila_tarjetas.setSpacing(8)
        fila_tarjetas.addWidget(self._tarjeta_finops(
            "📅 HOY", r_dia["total_costo"],
            r_dia["total_llamadas"], r_dia["total_tokens"]
        ))
        fila_tarjetas.addWidget(self._tarjeta_finops(
            "📆 ESTE MES", r_mes["total_costo"],
            r_mes["total_llamadas"], r_mes["total_tokens"]
        ))
        contenedor_tarjetas = QWidget()
        contenedor_tarjetas.setLayout(fila_tarjetas)
        self._layout_finops.addWidget(contenedor_tarjetas)

        # === Desglose por tipo (hoy) ===
        lbl_desglose = QLabel("Desglose hoy por tipo de operación:")
        lbl_desglose.setObjectName("subtitulo")
        self._layout_finops.addWidget(lbl_desglose)

        if r_dia["desglose_por_tipo"]:
            for item in r_dia["desglose_por_tipo"]:
                self._layout_finops.addWidget(self._fila_desglose_finops(item))
        else:
            sin = QLabel("_(sin actividad registrada hoy)_")
            sin.setObjectName("subtitulo")
            self._layout_finops.addWidget(sin)

        # === Info del modelo y precios ===
        info_modelo = QLabel(
            f"Modelo actual: <b>{info_precios['modelo'] or '(no configurado)'}</b> "
            f"({info_precios['proveedor']})"
        )
        info_modelo.setObjectName("subtitulo")
        info_modelo.setTextFormat(Qt.RichText)
        self._layout_finops.addWidget(info_modelo)

        precio_label = (
            f"Precio: ${info_precios['precio_input_por_millon']:.2f} input / "
            f"${info_precios['precio_output_por_millon']:.2f} output por 1M tokens"
        )
        if info_precios["override_activo"]:
            precio_label += " <i>(override desde config)</i>"
        precio_lbl = QLabel(precio_label)
        precio_lbl.setObjectName("subtitulo")
        precio_lbl.setTextFormat(Qt.RichText)
        self._layout_finops.addWidget(precio_lbl)

        actualizado_lbl = QLabel(
            f"<i>Precios hardcoded actualizados al {info_precios['actualizado_al']}. "
            f"Para ajustar, usa el override en config.json → finops.precios_override.</i>"
        )
        actualizado_lbl.setObjectName("subtitulo")
        actualizado_lbl.setTextFormat(Qt.RichText)
        actualizado_lbl.setWordWrap(True)
        self._layout_finops.addWidget(actualizado_lbl)

        # === Histórico últimos 5 días (gráfico simple en SVG) ===
        lbl_hist = QLabel("Histórico últimos 5 días:")
        lbl_hist.setObjectName("subtitulo")
        self._layout_finops.addWidget(lbl_hist)
        self._layout_finops.addWidget(self._grafico_finops(historico))

        # === Botones de acción ===
        fila_btns = QHBoxLayout()
        fila_btns.setSpacing(8)
        btn_refrescar = QPushButton("🔄 Refrescar")
        btn_refrescar.setToolTip("Vuelve a cargar los datos desde finops_data.json")
        btn_refrescar.clicked.connect(self._refrescar_finops)
        fila_btns.addWidget(btn_refrescar)

        btn_limpiar = QPushButton("🗑 Limpiar histórico")
        btn_limpiar.setObjectName("btn_limpiar_finops")
        btn_limpiar.setToolTip("Borra TODO el histórico de uso (acción irreversible)")
        btn_limpiar.clicked.connect(self._limpiar_historico_finops)
        fila_btns.addWidget(btn_limpiar)

        fila_btns.addStretch()
        contenedor_btns = QWidget()
        contenedor_btns.setLayout(fila_btns)
        self._layout_finops.addWidget(contenedor_btns)

    def _tarjeta_finops(self, titulo: str, costo: float,
                        llamadas: int, tokens: int) -> QWidget:
        """
        Construye una tarjeta con título y métricas (costo, llamadas, tokens).
        Se usa para Hoy y Este Mes.

        IMPORTANTE: usa QFrame (no QWidget) porque QFrame respeta el
        `background-color` y `border` del stylesheet de forma confiable.
        QWidget plano solo lo hace si se setea WA_StyledBackground, y aun
        así puede fallar al reconstruir dinámicamente.
        """
        # Formato de tokens: 4521 → "4.5k", 1234567 → "1.2M"
        if tokens >= 1_000_000:
            tokens_str = f"{tokens/1_000_000:.1f}M"
        elif tokens >= 1_000:
            tokens_str = f"{tokens/1_000:.1f}k"
        else:
            tokens_str = str(tokens)

        contenedor = QFrame()
        contenedor.setObjectName("tarjeta_finops")
        contenedor.setAttribute(Qt.WA_StyledBackground, True)  # cinturón de seguridad
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setObjectName("titulo_tarjeta_finops")
        layout.addWidget(lbl_titulo)

        lbl_costo = QLabel(f"${costo:.2f} USD")
        lbl_costo.setObjectName("costo_tarjeta_finops")
        layout.addWidget(lbl_costo)

        lbl_metricas = QLabel(f"{llamadas} llamadas · ~{tokens_str} tokens")
        lbl_metricas.setObjectName("subtitulo")
        layout.addWidget(lbl_metricas)

        return contenedor

    def _fila_desglose_finops(self, item: dict) -> QWidget:
        """
        Fila visual de desglose:
        [etiqueta]  [barra]  [$costo  XX%]
        """
        contenedor = QWidget()
        fila = QHBoxLayout(contenedor)
        fila.setContentsMargins(0, 2, 0, 2)
        fila.setSpacing(8)

        # Etiqueta
        lbl_etiq = QLabel(item["etiqueta"])
        lbl_etiq.setMinimumWidth(160)   # ← DIMENSIÓN: ancho etiqueta desglose FinOps
        fila.addWidget(lbl_etiq)

        # Barra de porcentaje (con QProgressBar truqueada)
        from PyQt5.QtWidgets import QProgressBar
        barra = QProgressBar()
        barra.setRange(0, 100)
        barra.setValue(int(item["porcentaje"]))
        barra.setTextVisible(False)
        barra.setFixedHeight(12)        # ← DIMENSIÓN: alto barra desglose FinOps
        barra.setObjectName("barra_finops")
        fila.addWidget(barra, stretch=1)

        # Costo y porcentaje a la derecha
        lbl_val = QLabel(f"${item['costo_usd']:.3f}  ({item['porcentaje']}%)")
        lbl_val.setMinimumWidth(110)    # ← DIMENSIÓN: ancho columna valor desglose
        lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fila.addWidget(lbl_val)

        return contenedor

    def _grafico_finops(self, historico: list) -> QWidget:
        """
        Mini-gráfico de barras para 5 días.

        Usa QFrame (no QWidget) para que el `background-color` y `border`
        del stylesheet `QFrame#grafico_finops { ... }` se respete tanto en
        el render inicial como en reconstrucciones dinámicas. Sin esto,
        el QWidget puede ignorar el background y dejar el gráfico "abierto".
        """
        contenedor = QFrame()
        contenedor.setObjectName("grafico_finops")
        contenedor.setAttribute(Qt.WA_StyledBackground, True)  # cinturón de seguridad
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Calcular el máximo para escalar
        max_costo = max((d["costo_usd"] for d in historico), default=0.0)
        if max_costo == 0:
            sin = QLabel("(sin actividad en los últimos 5 días)")
            sin.setObjectName("subtitulo")
            sin.setAlignment(Qt.AlignCenter)
            layout.addWidget(sin)
            return contenedor

        from PyQt5.QtWidgets import QProgressBar
        for dia in historico:
            fila = QHBoxLayout()
            fila.setSpacing(8)

            # Fecha (abreviada)
            lbl_dia = QLabel(f"{dia['dia']} {dia['fecha'][-5:]}")
            lbl_dia.setMinimumWidth(70)    # ← DIMENSIÓN: ancho etiqueta dia gráfico
            fila.addWidget(lbl_dia)

            # Barra escalada
            barra = QProgressBar()
            pct = int((dia["costo_usd"] / max_costo) * 100) if max_costo else 0
            barra.setRange(0, 100)
            barra.setValue(pct)
            barra.setTextVisible(False)
            barra.setFixedHeight(14)        # ← DIMENSIÓN: alto barra gráfico FinOps
            barra.setObjectName("barra_finops")
            fila.addWidget(barra, stretch=1)

            # Costo
            lbl_costo = QLabel(f"${dia['costo_usd']:.2f}")
            lbl_costo.setMinimumWidth(60)   # ← DIMENSIÓN: ancho costo en gráfico
            lbl_costo.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            fila.addWidget(lbl_costo)

            wrap = QWidget()
            wrap.setLayout(fila)
            layout.addWidget(wrap)

        return contenedor

    def _refrescar_finops(self):
        """Recarga los datos del módulo FinOps."""
        self._construir_modulo_finops()

    def _limpiar_historico_finops(self):
        """
        Limpia el archivo de histórico FinOps. Pide confirmación antes de
        ejecutar la acción (irreversible).
        """
        respuesta = QMessageBox.question(
            self,
            "Confirmar limpieza",
            "Vas a borrar TODO el histórico de consumo de API.\n\n"
            "Esta acción es irreversible y no se puede deshacer.\n\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if respuesta != QMessageBox.Yes:
            return

        try:
            import finops
            if finops.limpiar_historico():
                QMessageBox.information(
                    self, "Histórico limpiado",
                    "El histórico de FinOps fue borrado correctamente."
                )
            else:
                QMessageBox.warning(
                    self, "Error",
                    "No se pudo limpiar el histórico. Revisa la consola."
                )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error limpiando: {e}")

        # Refrescar UI para mostrar el estado vacío
        self._construir_modulo_finops()

    def _parsear_lista(self, texto: str) -> list:
        """Convierte un QTextEdit con una entrada por línea en lista limpia (lowercase)."""
        items = []
        for linea in texto.split("\n"):
            limpia = linea.strip().lower()
            if limpia:
                items.append(limpia)
        # Eliminar duplicados manteniendo orden
        vistos = set()
        unicos = []
        for it in items:
            if it not in vistos:
                vistos.add(it)
                unicos.append(it)
        return unicos

    def _parsear_lista_procesos(self, texto: str) -> list:
        """
        Convierte un QTextEdit con un .exe por línea en lista limpia,
        preservando el caso original. Usa comparación case-insensitive
        solo para deduplicar.
        """
        items = []
        for linea in texto.split("\n"):
            limpia = linea.strip()
            if limpia:
                items.append(limpia)
        # Eliminar duplicados case-insensitive manteniendo orden y formato original
        vistos = set()
        unicos = []
        for it in items:
            clave = it.lower()
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(it)
        return unicos

    def _guardar(self):
        """Guarda los cambios al config.json y aplica en caliente."""
        # VALIDACIÓN BLOQUEANTE (antes de tocar el config):
        # El prompt de clasificación debe contener TODOS los placeholders
        # críticos. Si no es así, se rechaza el guardado.
        prompt_clas_textarea = self.txt_prompt_clasificacion.toPlainText().strip()
        # Solo validar si el usuario escribió algo (vacío = se usará el default,
        # lo cual siempre es válido).
        if prompt_clas_textarea:
            es_valido, faltantes = validar_prompt_clasificacion(prompt_clas_textarea)
            if not es_valido:
                placeholders_faltantes = "\n".join(
                    f"  • {{{ph}}}" for ph in faltantes
                )
                QMessageBox.critical(
                    self,
                    "❌ Prompt de clasificación inválido",
                    "No se puede guardar: el prompt de clasificación está "
                    "incompleto.\n\n"
                    f"Faltan los siguientes placeholders obligatorios:\n"
                    f"{placeholders_faltantes}\n\n"
                    "Agrega los placeholders faltantes (con sus llaves textuales) "
                    "o presiona '↺ Restaurar default' para volver a la plantilla "
                    "por defecto."
                )
                return  # ← Bloqueo del guardado; el config.json no se modifica

        # Validación bloqueante de los prompts de imagen (actividad y reunión).
        # Mismo principio: vacío es válido (usa default); con contenido debe
        # incluir {titulo_ventana}.
        prompt_img_act_textarea = self.txt_prompt_img_actividad.toPlainText().strip()
        prompt_img_reu_textarea = self.txt_prompt_img_reunion.toPlainText().strip()

        for textarea_valor, nombre_legible in [
            (prompt_img_act_textarea, "actividad"),
            (prompt_img_reu_textarea, "reunión"),
        ]:
            if textarea_valor:
                es_valido, faltantes = validar_prompt_imagen(textarea_valor)
                if not es_valido:
                    placeholders_faltantes = "\n".join(
                        f"  • {{{ph}}}" for ph in faltantes
                    )
                    QMessageBox.critical(
                        self,
                        f"❌ Prompt de imagen ({nombre_legible}) inválido",
                        f"No se puede guardar: el prompt de imagen de "
                        f"{nombre_legible} está incompleto.\n\n"
                        f"Faltan los siguientes placeholders obligatorios:\n"
                        f"{placeholders_faltantes}\n\n"
                        "Agrega los placeholders faltantes (con sus llaves "
                        "textuales) o presiona '↺ Restaurar default'."
                    )
                    return  # ← Bloqueo del guardado

        try:
            # Releer config para no pisar otros campos modificados
            with open(self._ruta_config, encoding="utf-8") as f:
                cfg = json.load(f)

            # Listas de procesos (.exe) — preservan caso original
            cfg["lista_blanca_procesos"] = self._parsear_lista_procesos(self.txt_blanca.toPlainText())
            cfg["lista_negra_procesos"]  = self._parsear_lista_procesos(self.txt_negra.toPlainText())
            # Keywords de browser/UWP — lowercase
            cfg["palabras_clave_laborales_browser"] = self._parsear_lista(self.txt_browser.toPlainText())
            cfg["keywords_bloqueadas_browser"]      = self._parsear_lista(self.txt_browser_bloqueadas.toPlainText())
            # Personas conocidas — preserva mayúsculas usando _parsear_lista_procesos
            cfg["personas_conocidas"] = self._parsear_lista_procesos(self.txt_personas.toPlainText())
            cfg["dias_contexto_chat"] = self.spin_contexto.value()
            cfg.setdefault("alertas", {})["inactividad_dias"] = self.spin_alerta.value()

            # System prompt: si el textarea coincide con el default o está
            # vacío, guardamos cadena vacía para que se use el default del
            # módulo. Si tiene contenido distinto, guardamos lo escrito.
            prompt_textarea = self.txt_system_prompt.toPlainText().strip()
            if not prompt_textarea or prompt_textarea == SYSTEM_PROMPT.strip():
                cfg["system_prompt"] = ""
            else:
                cfg["system_prompt"] = prompt_textarea

            # Prompt de clasificación: misma lógica. Si está vacío o coincide
            # con el default, persistimos cadena vacía. Si difiere, guardamos
            # el contenido (ya validado al inicio del método).
            if not prompt_clas_textarea or prompt_clas_textarea == PROMPT_CLASIFICACION_DEFAULT.strip():
                cfg["prompt_clasificacion"] = ""
            else:
                cfg["prompt_clasificacion"] = prompt_clas_textarea

            # Prompts de imagen: misma lógica de "vacío o == default → ''".
            if not prompt_img_act_textarea or prompt_img_act_textarea == PROMPT_IMAGEN_ACTIVIDAD_DEFAULT.strip():
                cfg["prompt_imagen_actividad"] = ""
            else:
                cfg["prompt_imagen_actividad"] = prompt_img_act_textarea

            if not prompt_img_reu_textarea or prompt_img_reu_textarea == PROMPT_IMAGEN_REUNION_DEFAULT.strip():
                cfg["prompt_imagen_reunion"] = ""
            else:
                cfg["prompt_imagen_reunion"] = prompt_img_reu_textarea

            # Guardar modelo de IA seleccionado para el proveedor activo
            proveedor_activo = cfg.get("ia_proveedor", "claude")
            modelo_nuevo = self.combo_modelo.currentText().strip()
            if modelo_nuevo:
                cfg.setdefault("ia_modelos", {})[proveedor_activo] = modelo_nuevo

            # Tema visual seleccionado
            tema_id = self.combo_tema.currentData()
            if tema_id and tema_id in temas.IDS_VALIDOS:
                cfg["tema_visual"] = tema_id

            with open(self._ruta_config, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            # Como el tema queda persistido en config, ya no necesitamos
            # restaurar el "tema original" en reject(). Olvidamos el backup.
            if hasattr(self, "_tema_original"):
                del self._tema_original

            # Aplicar tema en caliente a la ventana principal
            widget_parent = self.parent()
            while widget_parent is not None:
                if hasattr(widget_parent, "_aplicar_estilo"):
                    try:
                        widget_parent._aplicar_estilo()
                    except Exception:
                        pass
                    break
                widget_parent = widget_parent.parent()

            # Aplicar en caliente — recargar config en gestor_chat
            if self.gestor_chat:
                self.gestor_chat.recargar_config()
            # El monitor llama cargar_config() en cada ciclo (1 seg),
            # así que las listas toman efecto automáticamente.

            # Aplicar modelo en caliente al cliente IA global
            modelo_aplicado = False
            if modelo_nuevo:
                try:
                    cliente = get_cliente()
                    if cliente is not None:
                        cliente.modelo = modelo_nuevo
                        modelo_aplicado = True
                except Exception:
                    # Si get_cliente no está disponible o falla, el cambio queda
                    # en config y se aplicará en el próximo arranque.
                    modelo_aplicado = False

            msg_modelo = (
                f"• Modelo IA ({modelo_nuevo}): aplicado en caliente\n"
                if modelo_aplicado else
                f"• Modelo IA ({modelo_nuevo}): aplicará en el próximo arranque\n"
            ) if modelo_nuevo else ""

            QMessageBox.information(
                self, "Guardado",
                "Configuración guardada ✅\n\n"
                "• Listas, días de contexto, prompt del agente y tema visual: aplicados en caliente\n"
                f"{msg_modelo}"
                "• Días alerta inactividad: aplicarán en el próximo arranque"
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo guardar:\n{e}")
