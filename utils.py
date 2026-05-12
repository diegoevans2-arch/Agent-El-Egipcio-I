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
