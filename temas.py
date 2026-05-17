"""
temas.py
Catálogo de temas visuales (skins) del agente.

Cada tema define una paleta semántica completa: fondos, textos, acentos,
botones de acción (éxito/peligro/advertencia), bordes. La paleta es
idéntica en estructura entre temas, así un mismo stylesheet sirve para
todos los temas con solo cambiar la paleta.

Uso:
    from temas import obtener_paleta_activa, ID_DEFAULT

    paleta = obtener_paleta_activa()              # lee de config.json
    color_fondo = paleta["fondo_principal"]

Para agregar un tema nuevo:
    1. Añade su id en TEMAS con la paleta completa.
    2. Asegúrate de definir TODOS los campos del DEFAULT.
"""

from typing import Optional

try:
    from utils import cargar_config
except ImportError:
    # Si utils no está disponible (tests fuera del agente), no falla
    def cargar_config():
        return {}


# ===========================================================================
# Identificadores de tema (los valores válidos para config.tema_visual)
# ===========================================================================

ID_MOCHA          = "mocha"
ID_LATTE          = "latte"
ID_DRACULA        = "dracula"
ID_NORD           = "nord"
ID_ALTO_CONTRASTE = "alto_contraste"

ID_DEFAULT = ID_MOCHA   # el actual de la app

IDS_VALIDOS = (ID_MOCHA, ID_LATTE, ID_DRACULA, ID_NORD, ID_ALTO_CONTRASTE)

# Metadatos para mostrar en la UI (selector de tema)
METADATOS = {
    ID_MOCHA:          {"emoji": "🌙",  "nombre": "Catppuccin Mocha",
                        "descripcion": "Oscuro azulado (actual)"},
    ID_LATTE:          {"emoji": "🌿",  "nombre": "Catppuccin Latte",
                        "descripcion": "Claro azulado (mismo lenguaje)"},
    ID_DRACULA:        {"emoji": "🧛",  "nombre": "Dracula",
                        "descripcion": "Oscuro violeta para devs"},
    ID_NORD:           {"emoji": "🌊",  "nombre": "Nord",
                        "descripcion": "Oscuro escandinavo azul-gris"},
    ID_ALTO_CONTRASTE: {"emoji": "⚡",  "nombre": "Alto contraste",
                        "descripcion": "Negro + verde fosforescente (accesibilidad)"},
}


# ===========================================================================
# Paletas
# ===========================================================================
# Cada paleta DEBE definir estos campos:
#
#   fondo_principal       Color base de ventanas, popups, fondo del scroll.
#   fondo_secundario      Barras inferiores, header, footers fijos.
#   fondo_terciario       Inputs, comboboxes, áreas de texto, cards.
#   fondo_hover           Hover/selección sobre fondo terciario.
#   borde                 Bordes de inputs/cards (gris medio).
#   borde_hover           Borde cuando hover/focus (color de acento).
#   texto_principal       Texto base de párrafos y labels.
#   texto_subtitulo       Subtítulos, hints, info secundaria.
#   texto_atenuado        Texto deshabilitado / cerrado / muy secundario.
#   texto_inverso         Texto sobre fondos brillantes (botón éxito/peligro).
#   acento                Color principal: links, focus, títulos de sección,
#                         barras de progreso.
#   exito                 Botón guardar, activar, costo en tarjeta FinOps.
#   exito_hover           Hover del botón éxito.
#   peligro               Botón cerrar, limpiar, eliminar.
#   peligro_hover         Hover del botón peligro.
#   advertencia           Iconos de warning, alertas leves (no críticas).
# ---------------------------------------------------------------------------

PALETAS = {

    # ===========================================================
    # MOCHA (Catppuccin Mocha) — TEMA ACTUAL, NO CAMBIAR COLORES
    # ===========================================================
    ID_MOCHA: {
        "fondo_principal":  "#1e1e2e",
        "fondo_secundario": "#181825",
        "fondo_terciario":  "#313244",
        "fondo_hover":      "#45475a",
        "borde":            "#45475a",
        "borde_hover":      "#89b4fa",
        "texto_principal":  "#cdd6f4",
        "texto_subtitulo":  "#6c7086",
        "texto_atenuado":   "#45475a",
        "texto_inverso":    "#1e1e2e",
        "acento":           "#89b4fa",
        "exito":            "#a6e3a1",
        "exito_hover":      "#94d68f",
        "peligro":          "#f38ba8",
        "peligro_hover":    "#eb6f8d",
        "advertencia":      "#f9e2af",
        "scroll_handle":    "#585b70",
        "scroll_handle_hover": "#74c7ec",
        "selector_acento":  "#a6adc8",
    },

    # ===========================================================
    # LATTE (Catppuccin Latte) — CLARO
    # ===========================================================
    ID_LATTE: {
        "fondo_principal":  "#eff1f5",   # base
        "fondo_secundario": "#dce0e8",   # crust
        "fondo_terciario":  "#ccd0da",   # surface0
        "fondo_hover":      "#bcc0cc",   # surface1
        "borde":            "#bcc0cc",
        "borde_hover":      "#1e66f5",   # blue
        "texto_principal":  "#4c4f69",   # text
        "texto_subtitulo":  "#6c6f85",   # subtext0
        "texto_atenuado":   "#9ca0b0",   # overlay0
        "texto_inverso":    "#eff1f5",
        "acento":           "#1e66f5",   # blue
        "exito":            "#40a02b",   # green
        "exito_hover":      "#358d24",
        "peligro":          "#d20f39",   # red
        "peligro_hover":    "#b80c33",
        "advertencia":      "#df8e1d",   # yellow
        "scroll_handle":    "#9ca0b0",
        "scroll_handle_hover": "#7c7f93",
        "selector_acento":  "#5c5f77",
    },

    # ===========================================================
    # DRACULA — OSCURO VIOLETA
    # ===========================================================
    ID_DRACULA: {
        "fondo_principal":  "#282a36",
        "fondo_secundario": "#21222c",
        "fondo_terciario":  "#44475a",
        "fondo_hover":      "#6272a4",
        "borde":            "#44475a",
        "borde_hover":      "#bd93f9",
        "texto_principal":  "#f8f8f2",
        "texto_subtitulo":  "#6272a4",
        "texto_atenuado":   "#44475a",
        "texto_inverso":    "#282a36",
        "acento":           "#bd93f9",   # purple
        "exito":            "#50fa7b",   # green
        "exito_hover":      "#3edc6a",
        "peligro":          "#ff5555",   # red
        "peligro_hover":    "#e84444",
        "advertencia":      "#f1fa8c",   # yellow
        "scroll_handle":    "#6272a4",
        "scroll_handle_hover": "#8be9fd",
        "selector_acento":  "#bd93f9",
    },

    # ===========================================================
    # NORD — OSCURO FRÍO ESCANDINAVO
    # ===========================================================
    ID_NORD: {
        "fondo_principal":  "#2e3440",   # nord0
        "fondo_secundario": "#242933",
        "fondo_terciario":  "#3b4252",   # nord1
        "fondo_hover":      "#434c5e",   # nord2
        "borde":            "#4c566a",   # nord3
        "borde_hover":      "#88c0d0",   # nord8
        "texto_principal":  "#eceff4",   # nord6
        "texto_subtitulo":  "#81a1c1",   # nord9 (más claro para legibilidad)
        "texto_atenuado":   "#4c566a",
        "texto_inverso":    "#2e3440",
        "acento":           "#88c0d0",   # nord8 (frost)
        "exito":            "#a3be8c",   # nord14 (green)
        "exito_hover":      "#8eaa77",
        "peligro":          "#bf616a",   # nord11 (red)
        "peligro_hover":    "#a8525a",
        "advertencia":      "#ebcb8b",   # nord13 (yellow)
        "scroll_handle":    "#4c566a",
        "scroll_handle_hover": "#5e81ac",
        "selector_acento":  "#88c0d0",
    },

    # ===========================================================
    # ALTO CONTRASTE — NEGRO + VERDE FOSFORESCENTE (accesibilidad)
    # ===========================================================
    # Diseño: bordes blancos finos para delimitar zonas claramente,
    # verde brillante para acción/éxito, naranja brillante para peligro
    # (mejor contraste con fondo negro que rojo). Sin grises medios.
    ID_ALTO_CONTRASTE: {
        "fondo_principal":  "#000000",
        "fondo_secundario": "#0a0a0a",
        "fondo_terciario":  "#1a1a1a",
        "fondo_hover":      "#2a2a2a",
        "borde":            "#ffffff",   # bordes BLANCOS bien visibles
        "borde_hover":      "#00ff00",   # verde fosforescente
        "texto_principal":  "#ffffff",
        "texto_subtitulo":  "#cccccc",
        "texto_atenuado":   "#888888",
        "texto_inverso":    "#000000",
        "acento":           "#00ff00",   # verde fosforescente
        "exito":            "#00ff00",
        "exito_hover":      "#00cc00",
        "peligro":          "#ff8800",   # naranja brillante (mejor que rojo en negro)
        "peligro_hover":    "#cc6e00",
        "advertencia":      "#ffff00",
        "scroll_handle":    "#888888",
        "scroll_handle_hover": "#00ff00",
        "selector_acento":  "#ffffff",
    },
}


# ===========================================================================
# Helpers de acceso
# ===========================================================================

def obtener_paleta(tema_id: str) -> dict:
    """
    Retorna la paleta del tema dado. Si el id no es válido,
    cae al tema default (MOCHA) silenciosamente.
    """
    if tema_id in PALETAS:
        return dict(PALETAS[tema_id])
    if tema_id:
        print(f"[Temas] ⚠ Tema desconocido '{tema_id}' — usando default ({ID_DEFAULT}).")
    return dict(PALETAS[ID_DEFAULT])


def obtener_id_activo() -> str:
    """
    Lee el tema activo desde config.json. Si no hay campo `tema_visual`
    o el valor no es válido, retorna el id del tema default.
    """
    try:
        cfg = cargar_config() or {}
    except Exception:
        cfg = {}
    valor = cfg.get("tema_visual", ID_DEFAULT)
    if valor not in IDS_VALIDOS:
        return ID_DEFAULT
    return valor


def obtener_paleta_activa() -> dict:
    """Atajo que combina los dos anteriores."""
    return obtener_paleta(obtener_id_activo())


def listar_temas() -> list:
    """
    Retorna una lista de dicts con todos los temas disponibles, en orden de
    presentación, lista para alimentar un combobox:
        [
            {"id": "mocha", "emoji": "🌙", "nombre": "...", "descripcion": "..."},
            ...
        ]
    """
    return [
        {
            "id": tid,
            "emoji": METADATOS[tid]["emoji"],
            "nombre": METADATOS[tid]["nombre"],
            "descripcion": METADATOS[tid]["descripcion"],
        }
        for tid in IDS_VALIDOS
    ]


def es_tema_claro(tema_id: str) -> bool:
    """Retorna True si el tema es claro (útil para íconos/decisiones de UI)."""
    return tema_id == ID_LATTE
