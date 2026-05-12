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
from utils import cargar_config


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
    ruta_base = Path(cfg["ruta_base"]) / "bitacoras" / "imagenes"
    ruta_base.mkdir(parents=True, exist_ok=True)
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
        prompt = f"""Estás viendo la pantalla de un profesional universitario durante una reunión virtual.
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
    else:
        prompt = f"""Estás viendo la pantalla de un profesional universitario (área de datos/analytics).
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

    try:
        cliente = get_cliente()
        # Subo levemente max_tokens porque ahora también puede haber URLs
        texto = cliente.analizar_imagen(prompt, imagen_b64, max_tokens=400)
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
