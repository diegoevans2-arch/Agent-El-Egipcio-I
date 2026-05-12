"""
popup_login.py
Ventana de autenticación inicial del Agente LLM - El Egypcio.
Permite seleccionar proveedor de IA, ingresar API key y validarla
antes de abrir la ventana principal.
"""

import json
import threading
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont

from cliente_ia import ClienteIA, PROVEEDORES, MODELOS_PRINCIPALES, set_cliente


class _SenalesLogin(QObject):
    resultado_validacion = pyqtSignal(bool, str)  # ok, mensaje


class PopupLogin(QDialog):
    """
    Popup modal de autenticación.
    - Selector de proveedor (Claude / OpenAI / Gemini)
    - Campo de API key con toggle de visibilidad
    - Checkbox "Recordar credenciales"
    - Validación in situ al hacer clic en Conectar

    Uso:
        popup = PopupLogin()
        if popup.exec_() == QDialog.Accepted:
            # cliente IA ya está inicializado y disponible vía get_cliente()
            ...
        else:
            sys.exit(0)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ruta_config = Path(__file__).parent / "config.json"
        self._config = self._cargar_config_raw()
        self._senales = _SenalesLogin()
        self._senales.resultado_validacion.connect(self._on_resultado_validacion)
        self._validando = False

        self.setWindowTitle("🏛 El Egypcio — Autenticación")
        self.setMinimumWidth(440)                # ← DIMENSIÓN: ancho mínimo popup login
        self.setMinimumHeight(360)               # ← DIMENSIÓN: alto mínimo popup login
        self.resize(460, 380)                    # ← DIMENSIÓN: tamaño inicial popup login
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._construir_ui()
        self._aplicar_estilo()
        self._poblar_campos()

    # ------------------------------------------------------------------
    def _cargar_config_raw(self) -> dict:
        if not self._ruta_config.exists():
            return {}
        with open(self._ruta_config, encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    def _construir_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        # --- Header ---
        titulo = QLabel("🏛 El Egypcio")
        titulo.setFont(QFont("Segoe UI", 16, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        subt = QLabel("Conecta con tu proveedor de IA")
        subt.setObjectName("subt")
        subt.setAlignment(Qt.AlignCenter)
        layout.addWidget(subt)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)
        layout.addSpacing(6)

        # --- Selector de proveedor ---
        layout.addWidget(self._lbl("Proveedor de IA"))
        self.combo_proveedor = QComboBox()
        self.combo_proveedor.setMinimumHeight(34)  # ← DIMENSIÓN: alto combo proveedor
        for proveedor_id, info in PROVEEDORES.items():
            self.combo_proveedor.addItem(
                f"{info['icono']}  {info['nombre']}",
                userData=proveedor_id
            )
        self.combo_proveedor.currentIndexChanged.connect(self._on_cambio_proveedor)
        layout.addWidget(self.combo_proveedor)

        # --- API Key ---
        layout.addWidget(self._lbl("API Key"))
        fila_key = QHBoxLayout()
        self.campo_key = QLineEdit()
        self.campo_key.setEchoMode(QLineEdit.Password)
        self.campo_key.setPlaceholderText("sk-...")
        self.campo_key.setMinimumHeight(34)        # ← DIMENSIÓN: alto campo API key
        self.campo_key.returnPressed.connect(self._conectar)

        self.btn_toggle = QPushButton("👁")
        self.btn_toggle.setFixedSize(34, 34)       # ← DIMENSIÓN: tamaño botón toggle visibilidad
        self.btn_toggle.setToolTip("Mostrar / ocultar key")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.clicked.connect(self._toggle_visibilidad)

        fila_key.addWidget(self.campo_key)
        fila_key.addWidget(self.btn_toggle)
        layout.addLayout(fila_key)

        # --- Recordar credenciales ---
        self.chk_recordar = QCheckBox("Recordar credenciales en este equipo")
        self.chk_recordar.setChecked(True)
        layout.addWidget(self.chk_recordar)

        # --- Mensaje de estado ---
        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("estado")
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setMinimumHeight(36)       # ← DIMENSIÓN: alto label de estado
        layout.addWidget(self.lbl_estado)

        layout.addStretch()

        # --- Botones ---
        fila_btn = QHBoxLayout()
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setMinimumHeight(36)     # ← DIMENSIÓN: alto botones inferiores
        self.btn_cancelar.clicked.connect(self.reject)

        self.btn_conectar = QPushButton("✓ Conectar")
        self.btn_conectar.setObjectName("btn_conectar")
        self.btn_conectar.setMinimumHeight(36)
        self.btn_conectar.clicked.connect(self._conectar)

        fila_btn.addWidget(self.btn_cancelar)
        fila_btn.addStretch()
        fila_btn.addWidget(self.btn_conectar)
        layout.addLayout(fila_btn)

    def _lbl(self, texto: str) -> QLabel:
        lbl = QLabel(texto)
        lbl.setObjectName("etiqueta")
        return lbl

    # ------------------------------------------------------------------
    def _aplicar_estilo(self):
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI';
            }
            QLabel { font-size: 9pt; color: #cdd6f4; }
            QLabel#subt { color: #6c7086; font-size: 9pt; }
            QLabel#etiqueta { color: #89b4fa; font-size: 9pt; font-weight: bold; }
            QLabel#estado { font-size: 8pt; padding: 4px; }

            QLineEdit {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 10px;
                color: #cdd6f4;
                font-size: 10pt;
            }
            QLineEdit:focus { border-color: #89b4fa; }

            QComboBox {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 10px;
                color: #cdd6f4;
                font-size: 9pt;
            }
            QComboBox:hover { border-color: #89b4fa; }
            QComboBox QAbstractItemView {
                background-color: #313244;
                color: #cdd6f4;
                selection-background-color: #45475a;
            }

            QCheckBox { color: #cdd6f4; font-size: 9pt; spacing: 8px; }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #45475a;
                border-radius: 3px;
                background-color: #313244;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }

            QPushButton {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 16px;
                color: #cdd6f4;
                font-size: 9pt;
            }
            QPushButton:hover { background-color: #45475a; }
            QPushButton:checked { background-color: #89b4fa; color: #1e1e2e; }
            QPushButton#btn_conectar {
                background-color: #a6e3a1;
                color: #1e1e2e;
                font-weight: bold;
            }
            QPushButton#btn_conectar:hover { background-color: #94d68f; }
            QPushButton#btn_conectar:disabled {
                background-color: #45475a;
                color: #6c7086;
            }
        """)

    # ------------------------------------------------------------------
    def _poblar_campos(self):
        """Pre-rellena con datos guardados si existen."""
        proveedor_actual = self._config.get("ia_proveedor", "claude")

        # Seleccionar proveedor en el combo
        for i in range(self.combo_proveedor.count()):
            if self.combo_proveedor.itemData(i) == proveedor_actual:
                self.combo_proveedor.setCurrentIndex(i)
                break

        self._cargar_key_de_proveedor(proveedor_actual)

    def _cargar_key_de_proveedor(self, proveedor: str):
        """Carga la API key guardada para el proveedor seleccionado."""
        keys = self._config.get("ia_api_keys", {})
        self.campo_key.setText(keys.get(proveedor, ""))

    def _on_cambio_proveedor(self, _idx):
        proveedor = self.combo_proveedor.currentData()
        self._cargar_key_de_proveedor(proveedor)
        self.lbl_estado.setText("")
        self.lbl_estado.setStyleSheet("")

    def _toggle_visibilidad(self):
        if self.btn_toggle.isChecked():
            self.campo_key.setEchoMode(QLineEdit.Normal)
        else:
            self.campo_key.setEchoMode(QLineEdit.Password)

    # ------------------------------------------------------------------
    def _conectar(self):
        if self._validando:
            return

        proveedor = self.combo_proveedor.currentData()
        api_key   = self.campo_key.text().strip()

        if not api_key:
            self._mostrar_estado("⚠ Debes ingresar una API key", error=True)
            return

        # Modelo: usa el guardado para este proveedor o el default
        modelos_guardados = self._config.get("ia_modelos", {})
        modelo = modelos_guardados.get(proveedor, MODELOS_PRINCIPALES[proveedor])

        # UI: deshabilitar y mostrar estado
        self._validando = True
        self.btn_conectar.setEnabled(False)
        self.btn_cancelar.setEnabled(False)
        self.btn_conectar.setText("Validando...")
        self._mostrar_estado(f"⏳ Conectando con {PROVEEDORES[proveedor]['nombre']}...")

        # Validación en hilo separado
        def _worker():
            try:
                cliente = ClienteIA(proveedor=proveedor, api_key=api_key, modelo=modelo)
                ok, mensaje = cliente.validar_key()
                if ok:
                    set_cliente(cliente)
                    self._senales.resultado_validacion.emit(True, "OK")
                else:
                    self._senales.resultado_validacion.emit(False, mensaje)
            except Exception as e:
                self._senales.resultado_validacion.emit(False, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_resultado_validacion(self, ok: bool, mensaje: str):
        self._validando = False
        self.btn_conectar.setEnabled(True)
        self.btn_cancelar.setEnabled(True)
        self.btn_conectar.setText("✓ Conectar")

        if ok:
            self._mostrar_estado("✅ Conexión exitosa", error=False)
            self._guardar_si_corresponde()
            QTimer.singleShot(400, self.accept)
        else:
            mensaje_corto = mensaje[:200] if len(mensaje) > 200 else mensaje
            self._mostrar_estado(f"❌ Error: {mensaje_corto}", error=True)

    def _mostrar_estado(self, texto: str, error: bool = False):
        self.lbl_estado.setText(texto)
        if error:
            self.lbl_estado.setStyleSheet("color: #f38ba8;")
        elif "✅" in texto:
            self.lbl_estado.setStyleSheet("color: #a6e3a1;")
        else:
            self.lbl_estado.setStyleSheet("color: #f9e2af;")

    # ------------------------------------------------------------------
    def _guardar_si_corresponde(self):
        """Guarda credenciales en config.json si el checkbox está marcado."""
        proveedor = self.combo_proveedor.currentData()
        api_key   = self.campo_key.text().strip()

        # Releer config para no pisar otros cambios
        with open(self._ruta_config, encoding="utf-8") as f:
            cfg = json.load(f)

        cfg["ia_proveedor"] = proveedor

        if self.chk_recordar.isChecked():
            cfg.setdefault("ia_api_keys", {})[proveedor] = api_key
        # Si NO está marcado, NO guardamos esta key (pero conservamos otras existentes)

        # Asegurar que el modelo del proveedor exista en config
        cfg.setdefault("ia_modelos", {})
        if proveedor not in cfg["ia_modelos"]:
            cfg["ia_modelos"][proveedor] = MODELOS_PRINCIPALES[proveedor]

        with open(self._ruta_config, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Migración del config viejo al nuevo formato
# ---------------------------------------------------------------------------

def migrar_config_si_necesario():
    """
    Migra automáticamente config.json del formato viejo al nuevo:
    - api_key (raíz)         → ia_api_keys.claude
    - modelo (raíz)          → ia_modelos.claude
    - Agrega ia_proveedor: "claude"
    Conserva ambos formatos por seguridad la primera vez.
    """
    ruta = Path(__file__).parent / "config.json"
    if not ruta.exists():
        return

    with open(ruta, encoding="utf-8") as f:
        cfg = json.load(f)

    cambios = False

    # Migrar api_key viejo → ia_api_keys.claude
    if "api_key" in cfg and cfg["api_key"]:
        cfg.setdefault("ia_api_keys", {})
        if "claude" not in cfg["ia_api_keys"] or not cfg["ia_api_keys"]["claude"]:
            cfg["ia_api_keys"]["claude"] = cfg["api_key"]
            cambios = True

    # Migrar modelo viejo → ia_modelos.claude
    if "modelo" in cfg and cfg["modelo"]:
        cfg.setdefault("ia_modelos", {})
        if "claude" not in cfg["ia_modelos"]:
            cfg["ia_modelos"]["claude"] = cfg["modelo"]
            cambios = True

    # Agregar proveedor por defecto si no existe
    if "ia_proveedor" not in cfg:
        cfg["ia_proveedor"] = "claude"
        cambios = True

    # Asegurar estructura mínima
    cfg.setdefault("ia_api_keys", {"claude": "", "openai": "", "gemini": ""})
    cfg.setdefault("ia_modelos", {
        "claude": MODELOS_PRINCIPALES["claude"],
        "openai": MODELOS_PRINCIPALES["openai"],
        "gemini": MODELOS_PRINCIPALES["gemini"]
    })
    # Asegurar que las 3 claves existan en ia_api_keys
    for prov in ["claude", "openai", "gemini"]:
        cfg["ia_api_keys"].setdefault(prov, "")
        cfg["ia_modelos"].setdefault(prov, MODELOS_PRINCIPALES[prov])

    if cambios:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("[Login] Config migrado al nuevo formato multi-proveedor")
