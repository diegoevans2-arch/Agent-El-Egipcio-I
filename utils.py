"""
utils.py
Utilidades compartidas por todos los módulos del agente.
Centraliza la carga de configuración con lógica dinámica:
  - ruta_base:    config.json > carpeta del script
  - ruta_obsidian: config.json > detección automática en rutas típicas de Windows

NOTA: Ya no exige API key aquí. La autenticación se maneja vía popup_login.py
y el cliente IA queda disponible globalmente en cliente_ia.py.
"""

import os
import json
from pathlib import Path


# Rutas típicas de instalación de Obsidian en Windows
RUTAS_OBSIDIAN_WINDOWS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Obsidian" / "Obsidian.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Obsidian" / "Obsidian.exe",
    Path(os.environ.get("APPDATA", ""))      / "Obsidian" / "Obsidian.exe",
    Path("C:/Users")  / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Obsidian" / "Obsidian.exe",
    Path("C:/Users")  / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Programs" / "Obsidian" / "Obsidian.exe",
    Path("C:/Program Files/Obsidian/Obsidian.exe"),
    Path("C:/Program Files (x86)/Obsidian/Obsidian.exe"),
]


def detectar_obsidian() -> str:
    """Busca el ejecutable de Obsidian en rutas típicas de Windows."""
    for ruta in RUTAS_OBSIDIAN_WINDOWS:
        if ruta.exists():
            return str(ruta)
    return "obsidian"  # fallback PATH


def cargar_config() -> dict:
    """
    Carga config.json y aplica overrides dinámicos:
    - Ruta base: config.json > carpeta del script
    - Ruta Obsidian: config.json > detección automática
    """
    ruta_config = Path(__file__).parent / "config.json"

    if not ruta_config.exists():
        raise FileNotFoundError(f"No se encontró config.json en {ruta_config.parent}")

    with open(ruta_config, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Ruta base
    ruta_base = config.get("ruta_base", "").strip()
    if not ruta_base:
        config["ruta_base"] = str(Path(__file__).parent)

    # Ruta Obsidian (1 y 2 — para múltiples PCs)
    if not config.get("ruta_obsidian_1", "").strip():
        config["ruta_obsidian_1"] = detectar_obsidian()

    return config


# ===========================================================================
# Rutas del vault — punto único de verdad para la estructura de carpetas
# ===========================================================================
# Toda la organización física del vault de Obsidian se define AQUÍ. Ningún
# otro módulo debe hardcodear nombres de carpeta como "bitacoras" o "Task".
# Si la estructura del vault cambia en el futuro, se edita solo este bloque.
#
# Estructura actual del vault (ruta_base = raíz del vault, ej. "Naos/"):
#
#   Naos/
#   ├── bitacoras/        → bitácoras diarias
#   ├── snippets/         → snippets de código (en la raíz)
#   ├── imagenes/         → capturas de pantalla (en la raíz)
#   ├── proyectos/        → MOCs por proyecto, gantt_proyectos.md, gantt_data.json
#   ├── Task/             → @-prefix (decisiones, tareas, ...), objetos, personas, diccionario
#   ├── scripts/          → finops_data.json + scripts operativos del usuario
#   ├── Solicitudes/      → Data_Request.md
#   └── Manuales de Uso del Agente/  → documentación .md del agente
#
# Cada helper crea su carpeta si no existe (mkdir idempotente), de modo que
# el primer uso en una instalación nueva no falle por carpeta ausente.

# Nombres de carpeta (constantes para evitar typos y facilitar cambios)
_CARPETA_BITACORAS  = "bitacoras"
_CARPETA_PROYECTOS  = "proyectos"
_CARPETA_TASK       = "Task"
_CARPETA_SCRIPTS    = "scripts"
_CARPETA_SOLICITUDES = "Solicitudes"
_CARPETA_MANUALES   = "Manuales de Uso del Agente"
_SUBCARPETA_SNIPPETS = "snippets"
_SUBCARPETA_IMAGENES = "imagenes"


def _ruta_base() -> Path:
    """Retorna la ruta base (raíz del vault) resuelta desde config."""
    return Path(cargar_config()["ruta_base"])


def ruta_bitacoras(crear: bool = True) -> Path:
    """
    Carpeta de bitácoras diarias. (snippets/ e imagenes/ viven en la raíz
    del vault, no aquí.)
    """
    ruta = _ruta_base() / _CARPETA_BITACORAS
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_snippets(crear: bool = True) -> Path:
    """Carpeta de snippets de código, en la raíz del vault."""
    ruta = _ruta_base() / _SUBCARPETA_SNIPPETS
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_imagenes(crear: bool = True) -> Path:
    """Carpeta de capturas de pantalla, en la raíz del vault."""
    ruta = _ruta_base() / _SUBCARPETA_IMAGENES
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_proyectos(crear: bool = True) -> Path:
    """
    Carpeta de proyectos. Contiene los MOCs (.md por proyecto), el Gantt
    global (gantt_proyectos.md) y sus datos crudos (gantt_data.json).
    """
    ruta = _ruta_base() / _CARPETA_PROYECTOS
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_task(crear: bool = True) -> Path:
    """
    Carpeta Task. Contiene los archivos agregados de notas estructuradas
    (@decision → decisiones.md, etc.) y los archivos de referencia
    (objetos.md, personas.md, diccionario_datos.md).
    """
    ruta = _ruta_base() / _CARPETA_TASK
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_scripts(crear: bool = True) -> Path:
    """
    Carpeta de scripts operativos. Contiene finops_data.json (datos crudos
    de FinOps) junto a los scripts del usuario (ej. dataRequestNotifier.js).
    """
    ruta = _ruta_base() / _CARPETA_SCRIPTS
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_solicitudes(crear: bool = True) -> Path:
    """Carpeta de solicitudes de información (Data_Request.md)."""
    ruta = _ruta_base() / _CARPETA_SOLICITUDES
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_manuales(crear: bool = True) -> Path:
    """
    Carpeta de manuales del agente. Contiene los .md de documentación que
    el chat carga cuando el usuario pregunta sobre el funcionamiento.
    """
    ruta = _ruta_base() / _CARPETA_MANUALES
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def nombre_vault() -> str:
    """
    Retorna el nombre del vault de Obsidian, derivado del nombre de la
    carpeta raíz (ruta_base). Ej: si ruta_base es "...\\Naos", retorna "Naos".

    Esto evita hardcodear el nombre del vault, que puede variar entre
    máquinas (por eso el bug de "vault=bitacoras").

    Es robusto ante distintos separadores de ruta: normaliza tanto "\\"
    (Windows) como "/" (Unix/manual) antes de extraer el último segmento.
    """
    ruta = str(_ruta_base()).replace("\\", "/").rstrip("/")
    # El último segmento tras normalizar es el nombre de la carpeta del vault
    return ruta.split("/")[-1] if ruta else ""


def uri_obsidian(ruta_relativa_en_vault: str = "") -> str:
    """
    Construye un URI obsidian:// para abrir el vault (y opcionalmente un
    archivo dentro de él).

    Args:
        ruta_relativa_en_vault: ruta del archivo relativa a la raíz del
            vault, con separadores "/", SIN extensión .md.
            Ej: "bitacoras/bitacora_2026-06-26" o "proyectos/gantt_proyectos".
            Si se deja vacío, abre solo el vault.

    Returns:
        El URI obsidian:// listo para os.startfile().

    Nota: Obsidian usa el nombre del vault (no la ruta), y la ruta del
    archivo es relativa a la raíz del vault. Los espacios y caracteres
    especiales se codifican.
    """
    from urllib.parse import quote
    vault = quote(nombre_vault())
    if ruta_relativa_en_vault:
        archivo = quote(ruta_relativa_en_vault)
        return f"obsidian://open?vault={vault}&file={archivo}"
    return f"obsidian://open?vault={vault}"
