"""
captura.py
Toma screenshots y los analiza con el cliente IA unificado (Claude/OpenAI/Gemini).
Retorna una descripción estructurada de la actividad detectada.

Cambios Fase 1:
- Detección de URLs visibles en pantalla
- Filtrado contra dominios laborales configurables
"""

import base64
import json
import io
from datetime import datetime

try:
    from PIL import Image
except ImportError:
    raise ImportError("Instala Pillow: pip install Pillow")

try:
    import mss
except ImportError:
    raise ImportError("Instala mss: pip install mss")

from cliente_ia import get_cliente
from utils import cargar_config, ruta_imagenes


# ===========================================================================
# Prompts de análisis de imágenes — configurables desde la UI
# ===========================================================================
# Hay dos prompts distintos según el contexto de la captura:
#   - REUNIÓN  (es_reunion=True):  detecta si se proyecta contenido laboral
#   - ACTIVIDAD (es_reunion=False): describe la tarea laboral en pantalla
#
# Ambos son editables desde Configuraciones (claves `prompt_imagen_reunion`
# y `prompt_imagen_actividad` en config.json). Si no existen o son inválidos,
# se usan estos defaults hardcodeados.
#
# Placeholder obligatorio en ambos: {titulo_ventana}. Sin él, el LLM no sabe
# qué ventana está analizando y el prompt no puede funcionar.

PLACEHOLDERS_IMAGEN = ["titulo_ventana"]

PROMPT_IMAGEN_REUNION_DEFAULT = """Estás viendo la pantalla de un profesional universitario durante una reunión virtual.
Título de la ventana: "{titulo_ventana}"

Analiza la imagen y determina:
1. ¿Se está proyectando contenido laboral? (presentación, documento, dashboard, tabla, etc.)
2. Si SÍ hay proyección: describe brevemente qué se está mostrando (máximo 3 líneas)
3. Si NO hay proyección (solo cámaras, fondo virtual, pantalla de espera): responde solo "SIN_PROYECCION"
4. URLs visibles: si hay una barra de navegador o links visibles, lista las URLs completas que aparezcan.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "hay_proyeccion": true,
  "descripcion": "descripción del contenido o SIN_PROYECCION",
  "tipo_contenido": "presentación/dashboard/documento/tabla/otro/ninguno",
  "urls": ["url1", "url2"]
}}"""

PROMPT_IMAGEN_ACTIVIDAD_DEFAULT = """Estás viendo la pantalla de un profesional universitario (área de datos/analytics).
Título de la ventana activa: "{titulo_ventana}"

Describe brevemente qué tarea laboral está realizando. Sé específico pero conciso (máximo 2 líneas).
Enfócate en: ¿qué herramienta usa?, ¿qué está haciendo en ella?

Adicionalmente: si hay URLs visibles en la pantalla (barra de navegador, links abiertos, etc.),
lístalas en el campo "urls". Si no hay URLs, retorna lista vacía.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{
  "actividad": "descripción concisa de la tarea",
  "categoria": "SQL/Python/Dashboard/Reunión/Documentación/Email/Otro",
  "herramienta": "nombre de la herramienta o aplicación principal",
  "urls": ["url1", "url2"]
}}"""


def validar_prompt_imagen(template: str) -> tuple:
    """
    Valida que un template de prompt de imagen contenga el placeholder
    obligatorio {titulo_ventana}.

    Returns:
        (es_valido, faltantes): faltantes es lista de placeholders ausentes.
    """
    if not template or not isinstance(template, str):
        return False, list(PLACEHOLDERS_IMAGEN)
    faltantes = [
        ph for ph in PLACEHOLDERS_IMAGEN
        if "{" + ph + "}" not in template
    ]
    return (len(faltantes) == 0, faltantes)


def cargar_prompt_imagen(es_reunion: bool) -> str:
    """
    Carga el template del prompt de imagen desde config.json según el
    contexto (reunión o actividad). Si la clave no existe, está vacía o
    es inválida, retorna el default correspondiente.
    """
    clave = "prompt_imagen_reunion" if es_reunion else "prompt_imagen_actividad"
    default = (
        PROMPT_IMAGEN_REUNION_DEFAULT if es_reunion
        else PROMPT_IMAGEN_ACTIVIDAD_DEFAULT
    )
    try:
        config = cargar_config()
        custom = (config.get(clave) or "").strip()
        if not custom:
            return default
        valido, _ = validar_prompt_imagen(custom)
        if not valido:
            print(f"[Captura] ⚠ {clave} inválido en config — usando default")
            return default
        return custom
    except Exception as e:
        print(f"[Captura] Error leyendo {clave}: {e} — usando default")
        return default


def tomar_screenshot() -> str:
    """
    Captura el monitor seleccionado en config.json y la retorna como base64 (JPEG).
    - monitor_captura = 1 (default): monitor principal
    - monitor_captura = 2, 3...: monitor específico
    - monitor_captura = -1: todos los monitores (panorámico)
    """
    cfg = cargar_config()
    monitor_idx = cfg.get("monitor_captura", 1)

    with mss.mss() as sct:
        # Validar que el índice exista
        if monitor_idx == -1:
            # Capturar todos: índice 0 en mss es el combinado
            captura = sct.grab(sct.monitors[0])
        elif 1 <= monitor_idx < len(sct.monitors):
            captura = sct.grab(sct.monitors[monitor_idx])
        else:
            # Fallback al monitor principal
            captura = sct.grab(sct.monitors[1])

        # Convertir a PIL Image
        screenshot = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")

    # Reducir tamaño para no exceder límites de la API (max ~1MB)
    screenshot = screenshot.resize(
        (screenshot.width // 2, screenshot.height // 2)
    )
    buffer = io.BytesIO()
    screenshot.save(buffer, format="JPEG", quality=70)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def tomar_screenshot_y_guardar() -> tuple:
    """
    Versión para capturas manuales: toma el screenshot UNA VEZ y retorna:
    - ruta_relativa: path relativa al vault (para wikilink en .md)
    - imagen_b64: la versión reducida ya codificada para enviar al LLM

    La imagen se guarda en alta calidad en `bitacoras/imagenes/`.
    Esta función NO llama al LLM — solo I/O local (~200ms).
    """
    from pathlib import Path
    from datetime import datetime

    cfg = cargar_config()
    monitor_idx = cfg.get("monitor_captura", 1)

    with mss.mss() as sct:
        if monitor_idx == -1:
            captura = sct.grab(sct.monitors[0])
        elif 1 <= monitor_idx < len(sct.monitors):
            captura = sct.grab(sct.monitors[monitor_idx])
        else:
            captura = sct.grab(sct.monitors[1])

        # Imagen original en alta calidad (para guardar en disco)
        screenshot_full = Image.frombytes("RGB", captura.size, captura.bgra, "raw", "BGRX")

    # 1. Guardar PNG en alta calidad en bitacoras/imagenes/
    ruta_base = ruta_imagenes()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_archivo = f"captura_{timestamp}.png"
    ruta_completa = ruta_base / nombre_archivo
    screenshot_full.save(ruta_completa, format="PNG", optimize=True)

    # 2. Versión reducida para enviar al LLM (igual que tomar_screenshot)
    screenshot_reducido = screenshot_full.resize(
        (screenshot_full.width // 2, screenshot_full.height // 2)
    )
    buffer = io.BytesIO()
    screenshot_reducido.save(buffer, format="JPEG", quality=70)
    buffer.seek(0)
    imagen_b64 = base64.b64encode(buffer.read()).decode("utf-8")

    # Ruta relativa para el wikilink (Obsidian la entiende desde la raíz del vault)
    ruta_relativa = f"imagenes/{nombre_archivo}"
    print(f"[Captura] Imagen guardada: {ruta_relativa}")

    return ruta_relativa, imagen_b64


def _filtrar_urls_laborales(urls: list, dominios_laborales: list) -> list:
    """
    Filtra una lista de URLs dejando solo las que pertenecen a dominios laborales.
    La comparación es case-insensitive y por substring.
    """
    if not urls or not dominios_laborales:
        return []

    dominios_lower = [d.lower() for d in dominios_laborales]
    urls_filtradas = []
    vistas = set()  # deduplicar

    for url in urls:
        if not url or not isinstance(url, str):
            continue
        url_limpia = url.strip()
        if not url_limpia:
            continue
        url_lower = url_limpia.lower()
        # ¿Coincide con algún dominio laboral?
        for dom in dominios_lower:
            if dom in url_lower:
                if url_lower not in vistas:
                    vistas.add(url_lower)
                    urls_filtradas.append(url_limpia)
                break

    return urls_filtradas


def analizar_screenshot(titulo_ventana: str, es_reunion: bool, imagen_b64: str = None) -> dict:
    """
    Envía el screenshot al cliente IA activo y retorna la descripción estructurada.
    Funciona con cualquiera de los proveedores configurados (Claude/OpenAI/Gemini).
    """
    if imagen_b64 is None:
        imagen_b64 = tomar_screenshot()

    if es_reunion:
        template = cargar_prompt_imagen(es_reunion=True)
        default = PROMPT_IMAGEN_REUNION_DEFAULT
    else:
        template = cargar_prompt_imagen(es_reunion=False)
        default = PROMPT_IMAGEN_ACTIVIDAD_DEFAULT

    # Rellenar el placeholder. Si .format() falla (llaves accidentales en
    # un template custom), caemos al default sin romper la captura.
    try:
        prompt = template.format(titulo_ventana=titulo_ventana)
    except (KeyError, IndexError, ValueError) as e:
        print(f"[Captura] ⚠ Error formateando prompt de imagen: {e} — usando default")
        prompt = default.format(titulo_ventana=titulo_ventana)

    try:
        cliente = get_cliente()
        # FinOps: distinguimos capturas de reunión vs actividad normal
        tipo_op = "captura_reunion" if es_reunion else "captura_actividad"
        # Subo levemente max_tokens porque ahora también puede haber URLs
        texto = cliente.analizar_imagen(prompt, imagen_b64, max_tokens=400,
                                         tipo_operacion=tipo_op)
        # Limpiar posibles bloques markdown
        texto = texto.replace("```json", "").replace("```", "").strip()
        resultado = json.loads(texto)

        # Filtrar URLs contra dominios laborales (defensivo: el LLM puede
        # devolver URLs no laborales o no devolver el campo)
        cfg = cargar_config()
        dominios_laborales = cfg.get("dominios_laborales", [])
        urls_brutas = resultado.get("urls", []) or []
        resultado["urls"] = _filtrar_urls_laborales(urls_brutas, dominios_laborales)

        return resultado

    except json.JSONDecodeError:
        return {
            "actividad": "Actividad detectada (sin detalle)",
            "categoria": "Otro",
            "herramienta": titulo_ventana,
            "urls": []
        }
    except Exception as e:
        print(f"[Captura] Error al analizar screenshot: {e}")
        return {
            "actividad": f"Error al analizar: {str(e)[:80]}",
            "categoria": "Error",
            "herramienta": titulo_ventana,
            "urls": []
        }


def capturar_y_analizar(titulo_ventana: str, es_reunion: bool) -> dict:
    """Función principal: toma screenshot, lo analiza y retorna el resultado."""
    print(f"[Captura] Analizando: {titulo_ventana[:60]}...")
    imagen_b64 = tomar_screenshot()
    resultado = analizar_screenshot(titulo_ventana, es_reunion, imagen_b64)
    resultado["titulo_ventana"] = titulo_ventana
    resultado["timestamp"] = datetime.now().isoformat()
    resultado["es_reunion"] = es_reunion
    return resultado
