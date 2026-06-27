"""
bitacora.py
Gestiona la escritura y lectura de la bitácora diaria en Markdown.
Escritura inmediata a disco — no se pierde nada si el agente se cierra.

Cambios Fase 1:
- URLs laborales detectadas se escriben al final de cada entrada
- Frontmatter YAML al cierre de jornada (cálculo 100% local, cero API)
- Detección automática de código en notas manuales (SQL/Python/Bash/JSON/JS/YAML)
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

from utils import cargar_config, ruta_bitacoras, ruta_snippets, ruta_task
from gantt import actualizar_gantt


# ===========================================================================
# Detección de código en notas manuales
# ===========================================================================
# Patrones de palabras clave por lenguaje. Si la nota tiene >=2 líneas y
# coincide con suficientes patrones de un lenguaje, se envuelve como bloque
# de código de ese lenguaje.
# ---------------------------------------------------------------------------

# SQL: palabras clave típicas + estructura habitual
_PATRON_SQL = re.compile(
    r"\b(SELECT|FROM|WHERE|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|"
    r"ALTER\s+TABLE|DROP\s+TABLE|JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|"
    r"GROUP\s+BY|ORDER\s+BY|HAVING|UNION|WITH|CTE|CASE\s+WHEN|"
    r"COUNT\s*\(|SUM\s*\(|AVG\s*\(|MIN\s*\(|MAX\s*\()\b",
    re.IGNORECASE,
)

# Python: estructuras y palabras clave únicas del lenguaje
_PATRON_PYTHON = re.compile(
    r"(^\s*import\s+\w+|^\s*from\s+\w[\w\.]*\s+import|"
    r"^\s*def\s+\w+\s*\(|^\s*class\s+\w+|^\s*@\w+|"
    r"\bprint\s*\(|\breturn\s+|\bself\.|\bif\s+__name__\s*==|"
    r"\.append\(|\.iloc\[|\.loc\[|pd\.|np\.)",
    re.MULTILINE,
)

# Bash / comandos
_PATRON_BASH = re.compile(
    r"(^\s*\$\s+\w+|^\s*sudo\s+|^\s*pip\s+install|^\s*npm\s+|^\s*git\s+\w+|"
    r"^\s*cd\s+|^\s*ls\s+|^\s*cp\s+|^\s*mv\s+|^\s*rm\s+|^\s*mkdir\s+|"
    r"^\s*chmod\s+|^\s*python\s+|^\s*python3\s+)",
    re.MULTILINE,
)

# JavaScript / TypeScript
_PATRON_JS = re.compile(
    r"(\bconst\s+\w+\s*=|\blet\s+\w+\s*=|\bvar\s+\w+\s*=|"
    r"\bfunction\s+\w+\s*\(|=>\s*[\{\(]|\bconsole\.log\s*\(|"
    r"\bdocument\.\w+|\bwindow\.\w+|\bawait\s+|\basync\s+function)",
    re.MULTILINE,
)

# JSON: empieza con { o [, tiene comillas y dos puntos
_PATRON_JSON = re.compile(r'^\s*[\{\[].*[\}\]]\s*$', re.DOTALL)

# YAML: tiene "clave: valor" en múltiples líneas
_PATRON_YAML = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_-]*\s*:\s*\S",
    re.MULTILINE,
)


def _detectar_lenguaje_codigo(texto: str):
    """
    Detecta si un texto parece código y retorna el lenguaje (str) o None.

    Reglas:
    - Mínimo 2 líneas de contenido (notas de 1 línea no se procesan como código)
    - Si la nota empieza con triple backtick, NO se procesa (el usuario ya
      formateó manualmente, se respeta su decisión).
    """
    if not texto or not texto.strip():
        return None

    # Si el usuario ya escribió un fence de código, no tocar
    if texto.strip().startswith("```"):
        return None

    lineas_no_vacias = [l for l in texto.split("\n") if l.strip()]
    if len(lineas_no_vacias) < 2:
        return None

    # Probar JSON primero (es el más estricto: parsearlo como tal)
    texto_strip = texto.strip()
    if _PATRON_JSON.match(texto_strip):
        try:
            json.loads(texto_strip)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass

    # Contar coincidencias por lenguaje
    scores = {
        "sql":    len(_PATRON_SQL.findall(texto)),
        "python": len(_PATRON_PYTHON.findall(texto)),
        "bash":   len(_PATRON_BASH.findall(texto)),
        "javascript": len(_PATRON_JS.findall(texto)),
    }

    # Tomar el lenguaje con más coincidencias, requiriendo umbral mínimo
    mejor_lenguaje = max(scores, key=scores.get)
    if scores[mejor_lenguaje] >= 2:
        return mejor_lenguaje

    # YAML como fallback (menor confianza, requiere >=3 coincidencias)
    if len(_PATRON_YAML.findall(texto)) >= 3:
        return "yaml"

    return None


def _formatear_nota_con_codigo(texto: str) -> str:
    """
    Si el texto parece código, lo envuelve en un bloque markdown.
    Si no, lo devuelve sin cambios.
    """
    lenguaje = _detectar_lenguaje_codigo(texto)
    if lenguaje is None:
        return texto
    contenido = texto.rstrip()
    return f"\n```{lenguaje}\n{contenido}\n```"


# ===========================================================================
# Snippets independientes (Fase 3)
# ===========================================================================
# Cuando una nota manual contiene código, en vez de inflar la bitácora del
# día, se guarda como archivo .md separado en bitacoras/snippets/ y la
# bitácora del día solo guarda un wikilink al snippet.
# ---------------------------------------------------------------------------

def _obtener_ruta_snippets() -> Path:
    """Retorna la carpeta donde se guardan los snippets, creándola si no existe."""
    return ruta_snippets()


def _crear_snippet(codigo: str, lenguaje: str, contexto: dict) -> str:
    """
    Crea un archivo .md de snippet con el código y contexto.

    Args:
        codigo: el texto de código (sin envolver en triple backtick)
        lenguaje: lenguaje detectado (sql, python, bash, etc.)
        contexto: dict con info opcional:
            - titulo_ventana: ventana activa al momento de la nota
            - proyecto: nombre del proyecto si hay match
            - origen: "comentario" | "captura_manual"
            - fuentes: lista de fuentes detectadas (Banner9, Athena...)
            - personas: lista de personas mencionadas

    Retorna:
        Ruta relativa al snippet desde la carpeta bitácoras (para wikilink),
        o cadena vacía si falló la creación.
    """
    try:
        ahora = datetime.now()
        timestamp = ahora.strftime("%Y-%m-%d_%H-%M-%S")
        nombre_archivo = f"{timestamp}_{lenguaje}.md"

        ruta_snippets = _obtener_ruta_snippets()
        ruta_completa = ruta_snippets / nombre_archivo

        # Construir el contenido del snippet
        proyecto = contexto.get("proyecto") or ""
        titulo_ventana = contexto.get("titulo_ventana") or ""
        origen = contexto.get("origen", "comentario")
        fuentes = contexto.get("fuentes") or []
        personas = contexto.get("personas") or []

        # Frontmatter
        fm_lines = ["---"]
        fm_lines.append(f"fecha: {ahora.strftime('%Y-%m-%d')}")
        fm_lines.append(f"hora: {ahora.strftime('%H:%M')}")
        fm_lines.append(f"lenguaje: {lenguaje}")
        fm_lines.append(f"tipo: snippet")
        fm_lines.append(f"origen: {origen}")
        if proyecto:
            fm_lines.append(f"proyecto: {proyecto}")
        if titulo_ventana:
            # Quotear porque puede tener caracteres especiales
            tv_escaped = titulo_ventana.replace('"', '\\"')
            fm_lines.append(f'contexto_ventana: "{tv_escaped}"')
        if fuentes:
            fm_lines.append(f"fuentes: [{', '.join(fuentes)}]")
        if personas:
            fm_lines.append(f"personas: [{', '.join(personas)}]")

        # Tags
        tags = ["snippet", f"snippet/{lenguaje}"]
        if proyecto:
            tags.append(f"proyecto/{_slug_tag(proyecto)}")
        for fuente in fuentes:
            tags.append(f"fuente/{_slug_tag(fuente)}")
        fm_lines.append(f"tags: [{', '.join(tags)}]")
        fm_lines.append("---")
        fm_lines.append("")

        # Cuerpo del snippet
        cuerpo = []
        # Título humano (timestamp + lenguaje + proyecto si hay)
        titulo_h1 = f"Snippet {lenguaje.upper()} — {ahora.strftime('%Y-%m-%d %H:%M')}"
        cuerpo.append(f"# {titulo_h1}")
        cuerpo.append("")

        # Bloque de código (lo principal)
        cuerpo.append(f"```{lenguaje}")
        cuerpo.append(codigo.rstrip())
        cuerpo.append("```")
        cuerpo.append("")

        # Sección de contexto
        cuerpo.append("## Contexto")
        if titulo_ventana:
            cuerpo.append(f"- 🪟 Ventana activa: `{titulo_ventana}`")
        if proyecto:
            slug_proy = _slug_tag(proyecto)
            cuerpo.append(f"- 🔗 Proyecto: [[{slug_proy}|{proyecto}]]")
        if fuentes:
            fuentes_links = ", ".join(f"[[{f}]]" for f in fuentes)
            cuerpo.append(f"- 📊 Fuentes: {fuentes_links}")
        if personas:
            personas_links = ", ".join(f"[[{p}]]" for p in personas)
            cuerpo.append(f"- 👥 Personas: {personas_links}")
        cuerpo.append(f"- 📅 Origen: {origen} en bitácora del "
                      f"[[bitacora_{ahora.strftime('%Y-%m-%d')}|{ahora.strftime('%Y-%m-%d')}]]")

        # Escribir archivo
        contenido_final = "\n".join(fm_lines) + "\n".join(cuerpo) + "\n"
        ruta_completa.write_text(contenido_final, encoding="utf-8")

        # Ruta relativa para el wikilink desde la bitácora del día
        # (Obsidian resuelve wikilinks relativos al vault, basta con el
        # path desde bitacoras/)
        ruta_wikilink = f"snippets/{timestamp}_{lenguaje}"
        print(f"[Bitácora] Snippet creado: {ruta_wikilink}")
        return ruta_wikilink

    except Exception as e:
        print(f"[Bitácora] Error al crear snippet: {e}")
        return ""


def _procesar_nota_con_snippet(texto: str, contexto: dict) -> tuple:
    """
    Procesa una nota detectando código y, si hay, crea un snippet aparte.

    Retorna (texto_para_bitacora, ruta_snippet_o_vacio):
    - Si no hay código: (texto_original, "")
    - Si hay código:    (wikilink al snippet, ruta_relativa)

    El texto que va a la bitácora del día es:
    - Si la nota es SOLO código → solo el wikilink al snippet
    - Si la nota tiene texto antes del código → ese texto + wikilink

    Esto permite mantener la nota humana en la bitácora ("probando esta query
    para ver matrículas") y la query como archivo separado.
    """
    if not texto or not texto.strip():
        return (texto, "")

    lenguaje = _detectar_lenguaje_codigo(texto)
    if lenguaje is None:
        return (texto, "")

    # Hay código → crear snippet
    ruta_snippet = _crear_snippet(texto, lenguaje, contexto)
    if not ruta_snippet:
        # Si falló la creación, dejar el código inline como fallback
        return (_formatear_nota_con_codigo(texto), "")

    # Wikilink hacia el snippet (formato Obsidian con alias amigable)
    nombre_visible = f"snippet {lenguaje}"
    wikilink = f"📎 [[{ruta_snippet}|{nombre_visible}]]"
    return (wikilink, ruta_snippet)


# ===========================================================================
# Wikilinks y tags inteligentes (Fase 2)
# ===========================================================================
# Listas hardcoded internas que se mantienen junto al código.
# Si en el futuro se necesita personalización por usuario, se puede mover
# todo esto a config.json sin cambiar la lógica.
# ---------------------------------------------------------------------------

# Mapeo de herramientas: cómo aparecen → forma canónica para el wikilink.
# La detección es case-insensitive y por substring sobre el campo
# "herramienta" del LLM y el título de ventana.
_MAPEO_HERRAMIENTAS = {
    # SQL / Datos
    "dbeaver":           "DBeaver",
    "athena":            "Athena",
    "amazon athena":     "Athena",
    "power bi":          "Power BI",
    "powerbi":           "Power BI",
    "pbi":               "Power BI",
    # Microsoft Office
    "excel":             "Excel",
    "microsoft excel":   "Excel",
    "word":              "Word",
    "microsoft word":    "Word",
    "powerpoint":        "PowerPoint",
    "power point":       "PowerPoint",
    "microsoft powerpoint": "PowerPoint",
    "outlook":           "Outlook",
    "microsoft outlook": "Outlook",
    "teams":             "Teams",
    "microsoft teams":   "Teams",
    "onedrive":          "OneDrive",
    "sharepoint":        "SharePoint",
    "onenote":           "OneNote",
    # Desarrollo
    "visual studio code": "VS Code",
    "vscode":             "VS Code",
    "vs code":            "VS Code",
    "github desktop":     "GitHub Desktop",
    "github":             "GitHub",
    "jupyter":            "Jupyter",
    "jupyter notebook":   "Jupyter",
    "python":             "Python",
    "anaconda":           "Anaconda",
    # Productividad / docs
    "obsidian":           "Obsidian",
    "notion":             "Notion",
    "claude":             "Claude",
    "chatgpt":            "ChatGPT",
    "gemini":             "Gemini",
    "deepseek":           "DeepSeek",
    "drawio":             "Draw.io",
    "draw.io":            "Draw.io",
    "diagrams.net":       "Draw.io",
    # Otros
    "zoom":               "Zoom",
    "google meet":        "Google Meet",
    "meet":               "Google Meet",
    "webex":              "Webex",
    "acrobat":            "Adobe Acrobat",
    "adobe acrobat":      "Adobe Acrobat",
}

# Mapeo de fuentes/sistemas detectables en el contenido (título o descripción)
# Estas se vuelven wikilinks y tags #fuente/...
_MAPEO_FUENTES = {
    "banner9":         "Banner9",
    "banner 9":        "Banner9",
    "banner":          "Banner9",
    "smartcampus":     "Smartcampus",
    "smart campus":    "Smartcampus",
    "aws":             "AWS",
    "amazon web services": "AWS",
    "athena":          "Athena",
    "confluence":      "Confluence",
    "jira":            "Jira",
    "uss":             "USS",
}

# Categorías reconocidas (de captura.py: SQL/Python/Dashboard/Reunión/Documentación/Email/Otro)
# Se normalizan para tags
_NORMALIZAR_CATEGORIA = {
    "sql":           "sql",
    "python":        "python",
    "dashboard":     "dashboard",
    "reunión":       "reunion",
    "reunion":       "reunion",
    "documentación": "documentacion",
    "documentacion": "documentacion",
    "email":         "email",
    "otro":          "otro",
}


def _slug_tag(texto: str) -> str:
    """
    Convierte un texto en un slug válido para tag de Obsidian:
    'Mi Proyecto' → 'mi-proyecto', 'Análisis Ventas' → 'analisis-ventas'.
    Quita tildes, espacios → guiones, todo en minúsculas.
    """
    s = _normalizar_tildes(texto.strip())
    # Reemplazar caracteres no alfanuméricos por guion
    s = re.sub(r"[^a-z0-9]+", "-", s)
    # Quitar guiones de los extremos
    return s.strip("-")


def _detectar_herramienta_canonica(herramienta_llm: str, titulo_ventana: str):
    """
    A partir del campo 'herramienta' del LLM y/o el título de ventana,
    intenta encontrar el nombre canónico de una herramienta conocida.
    Retorna el nombre canónico o None si no se reconoce.
    """
    textos = [(herramienta_llm or "").lower(), (titulo_ventana or "").lower()]
    for texto in textos:
        if not texto:
            continue
        for clave, canonico in _MAPEO_HERRAMIENTAS.items():
            # Substring match — clave debe aparecer como palabra completa
            # para evitar 'aws' matchee dentro de 'awsome'
            if re.search(r"\b" + re.escape(clave) + r"\b", texto):
                return canonico
    # Fallback permisivo: si el LLM dio un nombre y no está en la lista,
    # lo capitalizamos y usamos como wikilink igual.
    if herramienta_llm and herramienta_llm.strip():
        nombre = herramienta_llm.strip()
        # Quitar sufijos comunes que el LLM agrega
        nombre = re.sub(r"\s*\(.+\)\s*$", "", nombre)  # quita "(IA)", etc.
        if nombre and len(nombre) <= 40:
            return nombre
    return None


def _detectar_fuentes(texto: str) -> list:
    """
    Detecta fuentes/sistemas conocidos mencionados en un texto.
    Retorna lista de nombres canónicos (sin duplicados).
    """
    if not texto:
        return []
    texto_lower = texto.lower()
    encontradas = []
    vistas = set()
    for clave, canonico in _MAPEO_FUENTES.items():
        if re.search(r"\b" + re.escape(clave) + r"\b", texto_lower):
            if canonico not in vistas:
                vistas.add(canonico)
                encontradas.append(canonico)
    return encontradas


def _detectar_personas_en_entrada(texto: str, cfg: dict) -> list:
    """
    Versión específica por entrada de la detección de personas.
    Reusa la lógica de _detectar_personas pero solo sobre el texto de
    una entrada (no el .md completo del día).
    """
    return _detectar_personas(texto, cfg)


def _generar_bloque_tags(categoria: str, proyecto: str, fuentes: list,
                         es_reunion: bool) -> str:
    """
    Construye la línea final de tags para una entrada.
    Retorna string vacío si no hay nada relevante.
    """
    tags = []

    # Tag de categoría (siempre, si se reconoce)
    if es_reunion:
        tags.append("#reunion")
    elif categoria:
        cat_norm = _NORMALIZAR_CATEGORIA.get(categoria.strip().lower())
        if cat_norm:
            tags.append(f"#{cat_norm}")

    # Tag de proyecto (jerárquico)
    if proyecto:
        tags.append(f"#proyecto/{_slug_tag(proyecto)}")

    # Tags de fuentes (jerárquicos)
    for fuente in fuentes:
        tags.append(f"#fuente/{_slug_tag(fuente)}")

    if not tags:
        return ""
    return "🏷 " + " ".join(tags)


def _enriquecer_actividad_con_wikilinks(texto: str, herramienta_canonica: str,
                                         fuentes: list, personas: list) -> str:
    """
    Inserta wikilinks [[...]] en una descripción de actividad cuando se
    detectan menciones a fuentes (sistemas/datos) o personas.

    NOTA: Las herramientas (DBeaver, Excel, Power BI, etc.) NO se wikifican
    aquí. Esta decisión se tomó para reducir ruido en el grafo de Obsidian:
    las herramientas se usan a diario y no aportan conexiones conceptuales
    útiles entre notas. El parámetro `herramienta_canonica` se mantiene
    para compatibilidad de firma pero ya no se usa en el cuerpo.

    Para personas, usa matching tolerante a tildes: "Maria Lopez" en config
    matchea con "María López" en el texto. Cuando hay match parcial con
    tilde, se preserva la forma original del texto en el wikilink (con alias).

    No genera duplicados: si la palabra ya está dentro de un wikilink
    existente, no la vuelve a envolver.
    """
    if not texto:
        return texto

    resultado = texto

    # 1. Fuentes: matching directo (sin tildes especiales).
    #    Las herramientas se omiten intencionalmente — ver docstring.
    terminos_directos = list(fuentes)

    # Deduplicar manteniendo orden
    vistos = set()
    terminos_unicos = []
    for t in terminos_directos:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            terminos_unicos.append(t)

    # Ordenar por longitud descendente para evitar matches parciales
    terminos_unicos.sort(key=len, reverse=True)

    for termino in terminos_unicos:
        patron = (
            r"(?<!\[\[)(?<!\[)"
            r"\b" + re.escape(termino) + r"\b"
            r"(?!\]\])(?!\|)"
        )
        nuevo, n = re.subn(patron, f"[[{termino}]]", resultado, count=1,
                            flags=re.IGNORECASE)
        if n > 0:
            resultado = nuevo

    # 2. Personas: matching tolerante a tildes
    # Para cada persona, buscar las palabras en el texto (con o sin tildes)
    # y wikificar la primera secuencia que las contenga consecutivamente
    for persona in personas:
        palabras = persona.split()
        if not palabras:
            continue

        # Buscar la persona en el texto considerando posibles tildes
        # Construimos un patrón que matchee las palabras consecutivas con
        # cualquier variante de tildes
        patron_palabras = []
        for palabra in palabras:
            # Para cada letra, permitir su variante con/sin tilde
            letras_flex = []
            for c in palabra:
                c_lower = c.lower()
                if c_lower in "aeiou":
                    # Permitir variantes con tilde
                    if c_lower == "a":
                        letras_flex.append("[aáàäâ]")
                    elif c_lower == "e":
                        letras_flex.append("[eéèëê]")
                    elif c_lower == "i":
                        letras_flex.append("[iíìïî]")
                    elif c_lower == "o":
                        letras_flex.append("[oóòöô]")
                    elif c_lower == "u":
                        letras_flex.append("[uúùüû]")
                elif c_lower == "n":
                    letras_flex.append("[nñ]")
                else:
                    letras_flex.append(re.escape(c))
            patron_palabras.append("".join(letras_flex))

        # Patrón completo: palabras separadas por espacios u otros caracteres
        # de palabra
        patron_completo = (
            r"(?<!\[\[)(?<!\[)"
            r"\b" + r"\s+".join(patron_palabras) + r"\b"
            r"(?!\]\])(?!\|)"
        )

        # Buscar el match real en el texto para preservar tildes originales
        match = re.search(patron_completo, resultado, flags=re.IGNORECASE)
        if match:
            texto_original = match.group(0)
            if texto_original.lower() == persona.lower():
                # Match exacto sin tildes diferentes — wikilink simple
                reemplazo = f"[[{persona}]]"
            else:
                # Match con tildes diferentes — wikilink con alias para
                # preservar el texto original visible
                reemplazo = f"[[{persona}|{texto_original}]]"
            resultado = (
                resultado[:match.start()]
                + reemplazo
                + resultado[match.end():]
            )

    return resultado




def obtener_ruta_bitacora() -> Path:
    """Retorna la ruta del archivo .md del día actual."""
    ruta_base = ruta_bitacoras()
    fecha = datetime.now().strftime("%Y-%m-%d")
    return ruta_base / f"bitacora_{fecha}.md"


def iniciar_bitacora():
    """
    Crea o retoma la bitácora del día.
    Si ya existe, agrega una línea de continuación.
    """
    ruta = obtener_ruta_bitacora()
    fecha_legible = datetime.now().strftime("%A %d de %B de %Y")
    hora = datetime.now().strftime("%H:%M")

    if not ruta.exists():
        encabezado = f"""# Bitácora — {fecha_legible}

> Generada automáticamente por Agente LLM - El Egypcio

---

"""
        ruta.write_text(encabezado, encoding="utf-8")
        print(f"[Bitácora] Nueva bitácora creada: {ruta.name}")
    else:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"\n---\n▶ **Agente reiniciado — {hora}**\n---\n\n")
        print(f"[Bitácora] Retomando bitácora existente: {ruta.name}")

    return ruta


# ===========================================================================
# Frontmatter YAML — cálculo local al cierre de jornada
# ===========================================================================

# Mapa día_semana en español (datetime.strftime("%A") puede dar inglés
# dependiendo del locale del sistema)
_DIAS_ES = {
    0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
    4: "viernes", 5: "sábado", 6: "domingo"
}

# Regex para parsear las entradas existentes en el .md
_RE_DURACION = re.compile(r"⏱ \*\*Duración:\*\*\s*(?:(\d+)\s*min)?\s*(\d+)?s?")
_RE_HERRAMIENTA = re.compile(r"🔧 \*\*Herramienta:\*\*\s*(.+)")
_RE_PROYECTO = re.compile(r"🔗 \*\*Proyecto:\*\*\s*\[\[[^|\]]+\|([^\]]+)\]\]")
_RE_REUNION_HEADER = re.compile(r"^##\s+\d{2}:\d{2}\s*\|\s*🎥\s*Reunión", re.MULTILINE)
_RE_ENTRADA_HEADER = re.compile(r"^##\s+\d{2}:\d{2}\s*\|", re.MULTILINE)
_RE_CATEGORIA = re.compile(r"^##\s+\d{2}:\d{2}\s*\|\s*([^—\n]+?)\s*—", re.MULTILINE)


def _normalizar_tildes(texto: str) -> str:
    """
    Quita tildes y diacríticos para hacer matching robusto.
    'López' → 'lopez', 'María' → 'maria', etc.
    """
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _detectar_personas(contenido_md: str, cfg: dict) -> list:
    """
    Detecta nombres de personas mencionadas en el contenido del día con
    matching flexible: divide cada nombre configurado en palabras y
    verifica que TODAS aparezcan en el contenido (en cualquier orden,
    ignorando tildes y mayúsculas).

    Ejemplo: configurado "María López" matchea con:
    - "María Elena López Contreras"    ✅ (maria + lopez presentes)
    - "Reunión con María López"        ✅ (maria + lopez presentes)
    - "Reunión con María"              ❌ (falta lopez)

    Fuentes de candidatos (combinadas y deduplicadas):
    1. Lista global `personas_conocidas` en config.json (fuente principal)
    2. Patrón "Nombre Apellido" en descripción + objetivos de proyectos
       (con fallback a `palabras_clave` legacy)
    """
    candidatos = set()

    # Fuente 1: lista global
    for nombre in cfg.get("personas_conocidas", []) or []:
        if isinstance(nombre, str) and nombre.strip():
            candidatos.add(nombre.strip())

    # Fuente 2: extracción desde descripción + objetivos de proyectos
    # (con fallback a `palabras_clave` legacy para retrocompatibilidad)
    proyectos = cfg.get("proyectos", []) or []
    for p in proyectos:
        texto_proyecto = " ".join([
            p.get("descripcion", "") or "",
            p.get("objetivos", "") or "",
            p.get("palabras_clave", "") or "",   # legacy
        ])
        for m in re.finditer(r"\b([A-ZÁ-Ú][a-zá-ú]+\s+[A-ZÁ-Ú][a-zá-ú]+)\b", texto_proyecto):
            candidatos.add(m.group(1).strip())

    # Normalizar el contenido una sola vez
    contenido_normalizado = _normalizar_tildes(contenido_md)

    personas = []
    vistas = set()
    for nombre in candidatos:
        # Dividir en palabras (mínimo 3 letras para evitar partículas como "de", "la")
        palabras = [_normalizar_tildes(w) for w in nombre.split() if len(w) >= 3]
        if not palabras:
            continue

        # Verificar que TODAS las palabras aparezcan en el contenido
        # (usando límites de palabra para no matchear sustrings accidentales)
        todas_presentes = all(
            re.search(r"\b" + re.escape(p) + r"\b", contenido_normalizado)
            for p in palabras
        )

        if todas_presentes:
            clave = nombre.lower()
            if clave not in vistas:
                vistas.add(clave)
                personas.append(nombre)

    personas.sort()
    return personas


def _calcular_frontmatter(contenido_md: str) -> dict:
    """
    Calcula el frontmatter YAML a partir del contenido del .md del día.
    100% local, sin llamadas a API.
    """
    ahora = datetime.now()

    # Duraciones por entrada
    duraciones = []
    for m in _RE_DURACION.finditer(contenido_md):
        minutos = int(m.group(1)) if m.group(1) else 0
        segundos = int(m.group(2)) if m.group(2) else 0
        duraciones.append(minutos + segundos / 60.0)

    # Herramientas usadas (orden de aparición, dedup case-insensitive)
    # Limpia wikilinks [[X]] o [[X|Y]] dejando el nombre canónico
    herramientas = []
    vistas_h = set()
    for m in _RE_HERRAMIENTA.finditer(contenido_md):
        h = m.group(1).strip()
        # Si viene como wikilink [[X]] o [[X|Y]], extraer X (o Y si hay alias)
        m_wikilink = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", h)
        if m_wikilink:
            h = (m_wikilink.group(2) or m_wikilink.group(1)).strip()
        if h and h.lower() not in vistas_h:
            vistas_h.add(h.lower())
            herramientas.append(h)

    # Proyectos detectados con minutos acumulados
    proyectos_min = Counter()
    bloques = re.split(r"^##\s+", contenido_md, flags=re.MULTILINE)
    for bloque in bloques:
        m_dur = _RE_DURACION.search(bloque)
        m_proy = _RE_PROYECTO.search(bloque)
        if m_dur and m_proy:
            minutos = int(m_dur.group(1)) if m_dur.group(1) else 0
            segundos = int(m_dur.group(2)) if m_dur.group(2) else 0
            proyectos_min[m_proy.group(1).strip()] += minutos + segundos / 60.0

    proyectos_lista = [
        {"nombre": nom, "minutos": int(round(mins))}
        for nom, mins in proyectos_min.most_common()
    ]

    # Reuniones (header + duración acumulada)
    n_reuniones = len(_RE_REUNION_HEADER.findall(contenido_md))
    duracion_reuniones_min = 0.0
    for bloque in bloques:
        if _RE_REUNION_HEADER.search("## " + bloque):
            m_dur = _RE_DURACION.search(bloque)
            if m_dur:
                m_min = int(m_dur.group(1)) if m_dur.group(1) else 0
                m_seg = int(m_dur.group(2)) if m_dur.group(2) else 0
                duracion_reuniones_min += m_min + m_seg / 60.0

    # Total capturas
    n_capturas = len(_RE_ENTRADA_HEADER.findall(contenido_md))

    # Categorías
    categorias = Counter()
    for m in _RE_CATEGORIA.finditer(contenido_md):
        cat = m.group(1).strip()
        if "🎥" in cat:
            categorias["reunion"] += 1
        else:
            categorias[cat.lower()] += 1

    # Personas
    cfg = cargar_config()
    personas = _detectar_personas(contenido_md, cfg)

    horas_activas = round(sum(duraciones) / 60.0, 1)

    # Tags consolidados
    semana = ahora.isocalendar()
    tags = [
        "bitacora",
        f"dia/{_DIAS_ES[ahora.weekday()]}",
        f"semana/{semana.year}-W{semana.week:02d}",
    ]

    fm = {
        "fecha": ahora.strftime("%Y-%m-%d"),
        "dia_semana": _DIAS_ES[ahora.weekday()],
        "tipo": "bitacora-diaria",
        "horas_activas": horas_activas,
        "n_capturas": n_capturas,
        "n_reuniones": n_reuniones,
        "duracion_reuniones_min": int(round(duracion_reuniones_min)),
        "proyectos": proyectos_lista,
        "herramientas": herramientas,
        "personas": personas,
        "categorias": dict(categorias),
        "tags": tags,
    }
    return fm


def _serializar_frontmatter_yaml(fm: dict) -> str:
    """
    Serializa el frontmatter como YAML simple sin requerir librería pyyaml.
    Mantiene el orden definido en el dict y respeta los tipos esperados
    para que Obsidian Dataview lo lea correctamente.
    """
    lineas = ["---"]

    def fmt_str(s: str) -> str:
        # Strings con caracteres especiales se quotean
        if any(c in s for c in [":", "#", "[", "]", "{", "}", ",", "&", "*",
                                "!", "|", ">", "'", '"', "%", "@", "`"]):
            escaped = s.replace('"', '\\"')
            return f'"{escaped}"'
        return s

    for clave, valor in fm.items():
        if isinstance(valor, list):
            if not valor:
                lineas.append(f"{clave}: []")
            elif all(isinstance(v, str) for v in valor):
                items = ", ".join(fmt_str(v) for v in valor)
                lineas.append(f"{clave}: [{items}]")
            elif all(isinstance(v, dict) for v in valor):
                lineas.append(f"{clave}:")
                for d in valor:
                    primero = True
                    for k_inner, v_inner in d.items():
                        prefijo = "  - " if primero else "    "
                        if isinstance(v_inner, str):
                            lineas.append(f"{prefijo}{k_inner}: {fmt_str(v_inner)}")
                        else:
                            lineas.append(f"{prefijo}{k_inner}: {v_inner}")
                        primero = False
            else:
                lineas.append(f"{clave}: {valor}")
        elif isinstance(valor, dict):
            if not valor:
                lineas.append(f"{clave}: {{}}")
            else:
                lineas.append(f"{clave}:")
                for k_inner, v_inner in valor.items():
                    if isinstance(v_inner, str):
                        lineas.append(f"  {k_inner}: {fmt_str(v_inner)}")
                    else:
                        lineas.append(f"  {k_inner}: {v_inner}")
        elif isinstance(valor, str):
            lineas.append(f"{clave}: {fmt_str(valor)}")
        else:
            lineas.append(f"{clave}: {valor}")

    lineas.append("---\n")
    return "\n".join(lineas)


def _bitacora_tiene_frontmatter(contenido: str) -> bool:
    """Verifica si el archivo ya tiene un frontmatter YAML al inicio."""
    return contenido.lstrip().startswith("---")


def _quitar_frontmatter(contenido: str) -> str:
    """
    Si el contenido empieza con un frontmatter YAML (---...---), lo retira
    y retorna el resto del archivo. Si no hay frontmatter, retorna el
    contenido sin cambios.
    """
    if not _bitacora_tiene_frontmatter(contenido):
        return contenido
    # Buscar el cierre del frontmatter (segundo '---')
    # Saltamos el primer '---' y buscamos el siguiente al inicio de una línea
    sin_inicio = contenido.lstrip()
    if not sin_inicio.startswith("---"):
        return contenido
    # Encontrar el segundo '---' (cierre del frontmatter)
    lineas = sin_inicio.split("\n")
    fin_idx = None
    for i in range(1, len(lineas)):
        if lineas[i].strip() == "---":
            fin_idx = i
            break
    if fin_idx is None:
        return contenido  # frontmatter mal formado, no tocar
    # Resto del archivo después del cierre del frontmatter
    resto = "\n".join(lineas[fin_idx + 1:])
    # Quitar línea vacía justo después del frontmatter si existe
    return resto.lstrip("\n")


def _insertar_frontmatter(ruta: Path, fm_yaml: str, sobrescribir: bool = False):
    """
    Inserta el frontmatter al inicio del archivo.
    - Si `sobrescribir=False` (default): no toca si ya existe.
    - Si `sobrescribir=True`: reemplaza el frontmatter existente con uno nuevo.
    """
    if not ruta.exists():
        return
    contenido = ruta.read_text(encoding="utf-8")
    if _bitacora_tiene_frontmatter(contenido):
        if not sobrescribir:
            return
        # Quitar el viejo y poner el nuevo
        contenido_limpio = _quitar_frontmatter(contenido)
        ruta.write_text(fm_yaml + "\n" + contenido_limpio, encoding="utf-8")
    else:
        ruta.write_text(fm_yaml + "\n" + contenido, encoding="utf-8")


def regenerar_frontmatter(ruta: Path = None) -> bool:
    """
    Recalcula y reescribe el frontmatter de la bitácora indicada
    (por defecto, la del día actual).

    Útil para refrescar el frontmatter cuando se actualiza la lista de
    personas conocidas u otra config sin esperar al cierre de jornada.

    Retorna True si tuvo éxito, False en caso contrario.
    """
    try:
        if ruta is None:
            ruta = obtener_ruta_bitacora()
        if not ruta.exists():
            return False

        contenido = ruta.read_text(encoding="utf-8")
        # Calcular SOBRE el contenido sin frontmatter (para no contar el
        # propio frontmatter como contenido)
        contenido_sin_fm = _quitar_frontmatter(contenido)
        fm = _calcular_frontmatter(contenido_sin_fm)
        fm_yaml = _serializar_frontmatter_yaml(fm)
        _insertar_frontmatter(ruta, fm_yaml, sobrescribir=True)
        print(f"[Bitácora] Frontmatter regenerado: "
              f"{fm['horas_activas']}h activas, "
              f"{fm['n_capturas']} capturas, "
              f"{fm['n_reuniones']} reuniones, "
              f"{len(fm['personas'])} personas")
        return True
    except Exception as e:
        print(f"[Bitácora] Error al regenerar frontmatter: {e}")
        return False


# ===========================================================================
# GestorBitacora
# ===========================================================================

class GestorBitacora:
    """
    Maneja el ciclo de vida de las entradas de la bitácora.
    Cada entrada tiene: inicio, análisis de Claude, duración calculada al cerrar.
    """

    def __init__(self):
        self.ruta = iniciar_bitacora()
        self._entrada_actual = None  # Dict con datos de la entrada en curso
        self._hora_inicio_actual = None
        self._bloque_cabecera = ""
        self._contexto_tags = {}  # Fase 2: contexto para generar tags al cierre

    def abrir_entrada(self, analisis: dict):
        """
        Inicia una nueva entrada en la bitácora.
        Si había una entrada anterior abierta, la cierra primero.

        Fase 2: enriquece la entrada con wikilinks automáticos
        (herramientas, fuentes, personas) y prepara los tags para el cierre.
        """
        ahora = datetime.now()

        # Cerrar entrada anterior si existe
        if self._entrada_actual is not None:
            self._cerrar_entrada_actual(ahora)

        self._entrada_actual = analisis
        self._hora_inicio_actual = ahora

        hora_str = ahora.strftime("%H:%M")
        titulo = analisis.get("titulo_ventana", "Desconocido")[:70]
        es_reunion = analisis.get("es_reunion", False)

        # ---- Fase 2: detectar términos para wikificar ----
        cfg = cargar_config()
        herramienta_llm = analisis.get("herramienta", "")
        actividad_texto = analisis.get("actividad", "") or analisis.get("descripcion", "")
        contexto_deteccion = " ".join([titulo, herramienta_llm, actividad_texto])

        herramienta_canonica = _detectar_herramienta_canonica(herramienta_llm, titulo)
        fuentes = _detectar_fuentes(contexto_deteccion)
        personas = _detectar_personas_en_entrada(contexto_deteccion, cfg)

        # Guardar el contexto para que _cerrar_entrada_actual genere los tags
        self._contexto_tags = {
            "categoria": analisis.get("categoria", ""),
            "fuentes": fuentes,
            "es_reunion": es_reunion,
            # 'proyecto' lo pone _cerrar_entrada_actual cuando se conoce
        }

        # ---- Construir cabecera ----
        if es_reunion:
            hay_proyeccion = analisis.get("hay_proyeccion", False)
            descripcion = analisis.get("descripcion", "")
            tipo = analisis.get("tipo_contenido", "ninguno")

            # Enriquecer el título con wikilinks de fuentes y personas
            # (las herramientas ya no se wikifican — ver
            # _enriquecer_actividad_con_wikilinks).
            titulo_render = _enriquecer_actividad_con_wikilinks(
                titulo, herramienta_canonica, fuentes, personas
            )

            lineas = [f"## {hora_str} | 🎥 Reunión — {titulo_render}"]
            if hay_proyeccion:
                desc_enriquecida = _enriquecer_actividad_con_wikilinks(
                    descripcion, herramienta_canonica, fuentes, personas
                )
                lineas.append(f"📋 **Contenido proyectado ({tipo}):** {desc_enriquecida}")
            else:
                lineas.append(f"📋 Sin contenido proyectado — solo audio/video")
        else:
            actividad = analisis.get("actividad", "Actividad no identificada")
            categoria = analisis.get("categoria", "Otro")

            # Herramienta como texto plano (NO wikilink) — para no inflar
            # el grafo de Obsidian con nodos de uso diario.
            # La actividad sí se enriquece con wikilinks de fuentes/personas.
            herramienta_render = herramienta_canonica or herramienta_llm
            actividad_render = _enriquecer_actividad_con_wikilinks(
                actividad, herramienta_canonica, fuentes, personas
            )

            lineas = [
                f"## {hora_str} | {categoria} — {titulo}",
                f"🔧 **Herramienta:** {herramienta_render}",
                f"📌 **Actividad:** {actividad_render}"
            ]

        # URLs laborales detectadas (común a reuniones y entradas normales)
        urls = analisis.get("urls", []) or []
        if urls:
            lineas.append("🔗 **URLs:**")
            for url in urls:
                lineas.append(f"  - {url}")

        self._bloque_cabecera = "\n".join(lineas)

        # Escribir cabecera al archivo
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(self._bloque_cabecera + "\n")

        print(f"[Bitácora] Entrada abierta: {hora_str} | {titulo[:40]}")

    def _cerrar_entrada_actual(self, hora_fin: datetime):
        """Agrega la duración a la entrada actualmente abierta."""
        if self._hora_inicio_actual is None:
            return

        duracion = hora_fin - self._hora_inicio_actual
        minutos = int(duracion.total_seconds() // 60)
        segundos = int(duracion.total_seconds() % 60)

        if minutos > 0:
            duracion_str = f"{minutos} min {segundos}s"
        else:
            duracion_str = f"{segundos}s"

        # Bloque completo para pasar al .md del proyecto si hay match
        bloque_completo_md = (
            f"{self._bloque_cabecera}\n"
            f"⏱ **Duración:** {duracion_str}"
        )

        # Clasificar actividad y actualizar Gantt
        proyecto_match = None
        if self._entrada_actual and minutos >= 2:
            titulo = self._entrada_actual.get("titulo_ventana", "")
            desc   = self._entrada_actual.get("actividad", "") or self._entrada_actual.get("descripcion", "")
            try:
                proyecto_match = actualizar_gantt(titulo, desc, minutos, bloque_completo_md)
            except Exception as e:
                print(f"[Bitácora] Error al clasificar: {e}")

        # ---- Fase 2: construir línea de tags ----
        contexto = getattr(self, "_contexto_tags", {}) or {}
        linea_tags = _generar_bloque_tags(
            categoria=contexto.get("categoria", ""),
            proyecto=proyecto_match or "",
            fuentes=contexto.get("fuentes", []),
            es_reunion=contexto.get("es_reunion", False),
        )

        # Escribir duración + wikilink + tags + separador
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(f"⏱ **Duración:** {duracion_str}\n")
            if proyecto_match:
                from proyectos import _slugify
                slug = _slugify(proyecto_match)
                f.write(f"🔗 **Proyecto:** [[{slug}|{proyecto_match}]]\n")
            if linea_tags:
                f.write(f"{linea_tags}\n")
            f.write("\n---\n\n")

        # Limpiar el contexto de tags para la siguiente entrada
        self._contexto_tags = {}

        print(f"[Bitácora] Entrada cerrada — duración: {duracion_str}")

    def _construir_contexto_snippet(self, origen: str = "comentario",
                                     titulo_ventana_override: str = "") -> dict:
        """
        Construye el dict de contexto que se pasa a _crear_snippet().
        Toma información de la entrada actualmente abierta (si existe)
        para enriquecer el snippet con proyecto, ventana, fuentes, personas.
        """
        contexto = {"origen": origen}

        # Título de ventana: prioridad al override (capturas manuales),
        # si no, usar el de la entrada actual
        if titulo_ventana_override:
            contexto["titulo_ventana"] = titulo_ventana_override
        elif self._entrada_actual:
            contexto["titulo_ventana"] = self._entrada_actual.get("titulo_ventana", "")

        # Proyecto: tomar del último contexto de tags (si existe match)
        # Esto se llena en _cerrar_entrada_actual, pero acá podemos usar
        # las fuentes y personas detectadas al abrir la entrada
        if hasattr(self, "_contexto_tags") and self._contexto_tags:
            contexto["fuentes"] = self._contexto_tags.get("fuentes", [])

        # Detectar personas en el texto + título de ventana
        cfg = cargar_config()
        texto_busqueda = " ".join([
            contexto.get("titulo_ventana", ""),
            self._entrada_actual.get("actividad", "") if self._entrada_actual else "",
            self._entrada_actual.get("descripcion", "") if self._entrada_actual else "",
        ])
        contexto["personas"] = _detectar_personas(texto_busqueda, cfg)

        return contexto

    def agregar_comentario(self, texto: str):
        """
        Agrega una nota manual a la entrada actual.

        Detecta automáticamente:
        - @objeto: NOMBRE [- descripción] → agrega tabla al diccionario
          y registra nota en la bitácora (Fase 5b)
        - Notas estructuradas con prefijo @tipo: → formato visual con emoji
          + tag (Fase 5)
        - Código → snippet independiente (Fase 3)
        - Texto normal → nota inline simple
        """
        if not texto or not texto.strip():
            return

        hora_str = datetime.now().strftime("%H:%M")

        # 1. ¿Es nota estructurada (@decision:, @tarea:, @objeto:, etc.)?
        tipo, contenido_estr = _detectar_nota_estructurada(texto)
        if tipo is not None:
            # Casos especiales: @objeto, @diccionario, @persona →
            # además de escribir nota, actualizan archivo de registro
            tipos_con_registro = {
                "objeto":      ("objetos",     agregar_objeto_a_md),
                "diccionario": ("diccionario", agregar_concepto_a_diccionario),
                "persona":     ("personas",    agregar_persona_a_md),
            }
            if tipo in tipos_con_registro:
                _, fn_agregar = tipos_con_registro[tipo]
                nombre, descripcion_inline = _procesar_entrada_estructurada(contenido_estr)
                if nombre:
                    # Actualizar el archivo de registro
                    fn_agregar(nombre, descripcion_inline)
                    # Escribir nota en bitácora con formato distintivo
                    info = _TIPOS_NOTA_ESTRUCTURADA[tipo]
                    if descripcion_inline:
                        linea = (
                            f"{info['emoji']} **{info['etiqueta']} ({hora_str}):** "
                            f"`{nombre}` — {descripcion_inline}"
                        )
                    else:
                        linea = (
                            f"{info['emoji']} **{info['etiqueta']} ({hora_str}):** "
                            f"`{nombre}`"
                        )
                    with open(self.ruta, "a", encoding="utf-8") as f:
                        f.write(linea + "\n")
                    return
                else:
                    # Si el formato no es válido, escribir como nota normal
                    with open(self.ruta, "a", encoding="utf-8") as f:
                        f.write(f"💬 **Nota ({hora_str}):** {texto}\n")
                    print(f"[Bitácora] @{tipo} sin nombre válido — guardado como nota normal")
                    return

            # Otros tipos estructurados: formato visual normal en bitácora
            # del día. Adicionalmente, si el tipo tiene archivo agregado
            # asignado (decision, tarea, acuerdo, idea, bloqueado, ticket,
            # pendiente), se acumula también en su archivo correspondiente.
            linea = _formatear_nota_estructurada(tipo, contenido_estr, hora_str)
            with open(self.ruta, "a", encoding="utf-8") as f:
                f.write(linea + "\n")

            if tipo in _ARCHIVOS_TASK and contenido_estr.strip():
                agregar_task_a_archivo(tipo, contenido_estr.strip())

            print(f"[Bitácora] Nota estructurada agregada: @{tipo}")
            return

        # 2. ¿Es código? → crear snippet (Fase 3)
        contexto_snippet = self._construir_contexto_snippet(origen="comentario")
        texto_para_bitacora, _ = _procesar_nota_con_snippet(texto, contexto_snippet)

        with open(self.ruta, "a", encoding="utf-8") as f:
            if texto_para_bitacora != texto:
                if texto_para_bitacora.startswith("📎"):
                    f.write(f"💬 **Nota ({hora_str}):** {texto_para_bitacora}\n")
                else:
                    f.write(f"💬 **Nota ({hora_str}):**{texto_para_bitacora}\n")
            else:
                f.write(f"💬 **Nota ({hora_str}):** {texto}\n")
        print(f"[Bitácora] Comentario agregado")

    def agregar_captura_manual(self, descripcion_claude: str, nota_usuario: str = "",
                                ruta_imagen: str = "", titulo_ventana: str = ""):
        """
        Registra una captura manual solicitada por el usuario.
        - La imagen (si se entrega) se inserta como wikilink en la bitácora
        - Si la nota del usuario es código, se crea snippet aparte (Fase 3)
        - Si es texto normal, se escribe inline como antes
        """
        hora_str = datetime.now().strftime("%H:%M")
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(f"📷 **Captura manual ({hora_str}):** {descripcion_claude}\n")
            if titulo_ventana:
                f.write(f"   🪟 Ventana: {titulo_ventana}\n")
            if ruta_imagen:
                # Wikilink de imagen (formato Obsidian)
                f.write(f"![[{ruta_imagen}]]\n")

            if nota_usuario:
                # Construir contexto para snippet (si la nota es código)
                contexto_snippet = self._construir_contexto_snippet(
                    origen="captura_manual",
                    titulo_ventana_override=titulo_ventana
                )
                texto_proc, _ = _procesar_nota_con_snippet(
                    nota_usuario, contexto_snippet
                )

                if texto_proc != nota_usuario:
                    # Es snippet o bloque de código fallback
                    if texto_proc.startswith("📎"):
                        f.write(f"   ✏️ Nota: {texto_proc}\n")
                    else:
                        f.write(f"   ✏️ Nota:{texto_proc}\n")
                else:
                    f.write(f"   ✏️ Nota: {nota_usuario}\n")
        print(f"[Bitácora] Captura manual registrada")

    def cerrar_jornada(self):
        """
        Cierra la última entrada y agrega resumen de cierre.
        Calcula y reescribe el frontmatter YAML al inicio del archivo,
        sobrescribiendo si ya existía (para que siempre quede actualizado
        con la config más reciente).

        Fase 4: además actualiza los MOCs de los proyectos que tuvieron
        actividad ese día.
        """
        ahora = datetime.now()
        if self._entrada_actual is not None:
            self._cerrar_entrada_actual(ahora)

        hora_str = ahora.strftime("%H:%M")
        with open(self.ruta, "a", encoding="utf-8") as f:
            f.write(f"\n---\n⏹ **Agente detenido — {hora_str}**\n")

        # Regenerar frontmatter (siempre, sobrescribiendo si existía)
        regenerar_frontmatter(self.ruta)

        # Fase 5: regenerar sección destacada del día (decisiones, tareas, etc.)
        try:
            regenerar_seccion_destacada(self.ruta)
        except Exception as e:
            print(f"[Bitácora] Error al regenerar sección destacada: {e}")

        # Fase 4: actualizar MOCs de proyectos con actividad ese día
        try:
            self._actualizar_mocs_del_dia()
        except Exception as e:
            print(f"[Bitácora] Error al actualizar MOCs: {e}")

        print(f"[Bitácora] Jornada cerrada — archivo: {self.ruta.name}")

    def _actualizar_mocs_del_dia(self):
        """
        Detecta los proyectos que aparecieron en la bitácora del día y
        actualiza sus MOCs (frontmatter ampliado, snippets, resumen).
        """
        try:
            contenido = self.ruta.read_text(encoding="utf-8")
        except Exception:
            return

        # Extraer nombres de proyecto desde los wikilinks tipo
        # 🔗 **Proyecto:** [[slug|Nombre Proyecto]]
        proyectos_con_actividad = set()
        for m in re.finditer(
            r"🔗 \*\*Proyecto:\*\*\s*\[\[[^|\]]+\|([^\]]+)\]\]",
            contenido,
        ):
            nombre = m.group(1).strip()
            if nombre:
                proyectos_con_actividad.add(nombre)

        if not proyectos_con_actividad:
            return

        # Importar dentro de la función para evitar import circular
        try:
            from proyectos import actualizar_mocs_de
            n = actualizar_mocs_de(list(proyectos_con_actividad))
            if n > 0:
                print(f"[Bitácora] MOCs actualizados: {n}/{len(proyectos_con_actividad)} proyectos")
        except ImportError:
            # proyectos.py no disponible (no debería pasar) — silencioso
            pass

    def leer_bitacora_hoy(self) -> str:
        """Retorna el contenido completo de la bitácora del día."""
        if self.ruta.exists():
            return self.ruta.read_text(encoding="utf-8")
        return ""

    def leer_bitacoras_recientes(self, dias: int = 5) -> str:
        """Retorna el contenido de las últimas N bitácoras para contexto del chat."""
        ruta_base = ruta_bitacoras()
        archivos = sorted(ruta_base.glob("bitacora_*.md"), reverse=True)[:dias]
        contenido = ""
        for archivo in archivos:
            contenido += f"\n\n{'='*50}\n"
            contenido += f"# {archivo.stem}\n"
            contenido += archivo.read_text(encoding="utf-8")
        return contenido


# ===========================================================================
# Fase 5: Notas estructuradas + Diccionario de datos
# ===========================================================================

# Tipos de notas estructuradas reconocidas (prefijos @)
# Cada uno tiene: emoji visual, tag para búsqueda, etiqueta legible
_TIPOS_NOTA_ESTRUCTURADA = {
    "decision":    {"emoji": "✅", "etiqueta": "DECISIÓN",    "tag": "decision"},
    "tarea":       {"emoji": "⏳", "etiqueta": "TAREA",       "tag": "tarea"},
    "acuerdo":     {"emoji": "🤝", "etiqueta": "ACUERDO",     "tag": "acuerdo"},
    "idea":        {"emoji": "💡", "etiqueta": "IDEA",        "tag": "idea"},
    "bloqueado":   {"emoji": "🚧", "etiqueta": "BLOQUEADO",   "tag": "bloqueado"},
    "ticket":      {"emoji": "🎫", "etiqueta": "TICKET",      "tag": "ticket"},
    "pendiente":   {"emoji": "📌", "etiqueta": "PENDIENTE",   "tag": "pendiente"},
    "objeto":      {"emoji": "📚", "etiqueta": "OBJETO",      "tag": "objeto"},
    "diccionario": {"emoji": "📖", "etiqueta": "DICCIONARIO", "tag": "diccionario"},
    "persona":     {"emoji": "👤", "etiqueta": "PERSONA",     "tag": "persona"},
}


# ---------------------------------------------------------------------------
# Archivos agregados por tipo de task
# ---------------------------------------------------------------------------
# Cada vez que el usuario registra un task con uno de estos prefijos, además
# de escribirse la línea en la bitácora del día, la misma entrada se acumula
# en un archivo agregado dedicado en bitacoras/. Esto permite tener un
# "registro maestro" por tipo (todas las decisiones, todas las tareas, etc.)
# que el chat puede cargar como contexto cuando el usuario pregunte por ello.
#
# NO incluye objeto/diccionario/persona porque esos ya tienen su propio
# archivo con lógica distinta (upsert por nombre).
_ARCHIVOS_TASK = {
    "decision":  ("decisiones.md", "✅ Decisiones",  "registro-decisiones"),
    "tarea":     ("tareas.md",     "⏳ Tareas",      "registro-tareas"),
    "acuerdo":   ("acuerdos.md",   "🤝 Acuerdos",    "registro-acuerdos"),
    "idea":      ("ideas.md",      "💡 Ideas",       "registro-ideas"),
    "bloqueado": ("bloqueados.md", "🚧 Bloqueados",  "registro-bloqueados"),
    "ticket":    ("tickets.md",    "🎫 Tickets",     "registro-tickets"),
    "pendiente": ("pendientes.md", "📌 Pendientes",  "registro-pendientes"),
}


def _detectar_nota_estructurada(texto: str):
    """
    Detecta si un texto inicia con un prefijo @tipo: y retorna sus partes.

    Retorna:
        - (None, None): si no es nota estructurada
        - (tipo, contenido): si lo es. Ej: ("decision", "Usaremos Banner9...")

    Acepta variantes:
        @decision: contenido
        @decisión: contenido    (con tilde)
        @ticket:PROY-1234       (sin espacio)
    """
    if not texto:
        return (None, None)

    # Patrón: @<palabra>: <resto>
    m = re.match(r"^\s*@([a-záéíóúñ]+)\s*:\s*(.+)$", texto.strip(),
                 re.IGNORECASE | re.DOTALL)
    if not m:
        return (None, None)

    tipo_raw = m.group(1).lower()
    contenido = m.group(2).strip()

    # Normalizar tildes y variantes
    tipo_norm = _normalizar_tildes(tipo_raw)
    if tipo_norm in _TIPOS_NOTA_ESTRUCTURADA:
        return (tipo_norm, contenido)

    return (None, None)


def _formatear_nota_estructurada(tipo: str, contenido: str, hora: str) -> str:
    """
    Formatea una nota estructurada para escribir en la bitácora.
    Retorna la línea markdown lista para escribir.
    """
    info = _TIPOS_NOTA_ESTRUCTURADA[tipo]
    emoji = info["emoji"]
    etiqueta = info["etiqueta"]
    return f"{emoji} **{etiqueta} ({hora}):** {contenido}"


def _extraer_notas_estructuradas_del_md(contenido_md: str) -> list:
    """
    Recorre el contenido de la bitácora del día y extrae todas las notas
    estructuradas escritas (líneas que empiezan con un emoji + etiqueta de tipo).

    Retorna lista de dicts: {emoji, etiqueta, hora, contenido, tipo}
    """
    if not contenido_md:
        return []

    notas = []
    # Construir patrón global: alguno de los emojis + etiqueta + (hora) + contenido
    emojis = "|".join(re.escape(info["emoji"]) for info in _TIPOS_NOTA_ESTRUCTURADA.values())
    etiquetas = "|".join(info["etiqueta"] for info in _TIPOS_NOTA_ESTRUCTURADA.values())

    patron = re.compile(
        r"^(" + emojis + r")\s+\*\*(" + etiquetas + r")\s*\((\d{2}:\d{2})\):\*\*\s*(.+)$",
        re.MULTILINE
    )

    for m in patron.finditer(contenido_md):
        emoji = m.group(1)
        etiqueta = m.group(2)
        hora = m.group(3)
        contenido = m.group(4).strip()

        # Encontrar el tipo basado en el emoji
        tipo = ""
        for k, v in _TIPOS_NOTA_ESTRUCTURADA.items():
            if v["emoji"] == emoji:
                tipo = k
                break

        notas.append({
            "tipo": tipo,
            "emoji": emoji,
            "etiqueta": etiqueta,
            "hora": hora,
            "contenido": contenido,
        })

    # Ordenar cronológicamente
    notas.sort(key=lambda n: n["hora"])
    return notas


def _construir_seccion_destacada(notas: list) -> str:
    """
    Construye el bloque markdown de la sección destacada del día con
    todas las decisiones, tareas, acuerdos, etc.
    """
    if not notas:
        return ""

    # Agrupar por tipo, orden definido
    orden_tipos = ["decision", "acuerdo", "tarea", "pendiente", "bloqueado", "idea", "ticket"]
    por_tipo = {t: [] for t in orden_tipos}
    for nota in notas:
        if nota["tipo"] in por_tipo:
            por_tipo[nota["tipo"]].append(nota)

    lineas = ["## 📌 Decisiones, tareas y acuerdos del día", ""]

    for tipo in orden_tipos:
        items = por_tipo[tipo]
        if not items:
            continue
        for nota in items:
            tag = _TIPOS_NOTA_ESTRUCTURADA[tipo]["tag"]
            linea = (
                f"- {nota['emoji']} **{nota['etiqueta']}** ({nota['hora']}): "
                f"{nota['contenido']} #{tag}"
            )
            lineas.append(linea)

    return "\n".join(lineas)


# Marcadores para la sección destacada del día
_MARKER_DESTACADO_INI = "<!-- DESTACADO_INICIO -->"
_MARKER_DESTACADO_FIN = "<!-- DESTACADO_FIN -->"


def _insertar_seccion_destacada(ruta: Path, bloque: str):
    """
    Inserta o reemplaza la sección destacada del día en la bitácora.
    Va justo después del frontmatter (o al inicio si no hay frontmatter)
    y antes del primer encabezado '## HH:MM | ...'.

    Si no hay notas, elimina la sección si existía.
    """
    if not ruta.exists():
        return
    contenido = ruta.read_text(encoding="utf-8")

    bloque_completo = (
        f"{_MARKER_DESTACADO_INI}\n"
        f"{bloque}\n"
        f"{_MARKER_DESTACADO_FIN}\n"
    )

    # ¿Ya existe la sección? → reemplazar
    patron = (
        re.escape(_MARKER_DESTACADO_INI)
        + r".*?"
        + re.escape(_MARKER_DESTACADO_FIN)
        + r"\n*"
    )
    if re.search(patron, contenido, flags=re.DOTALL):
        if bloque.strip():
            nuevo = re.sub(patron, bloque_completo + "\n", contenido,
                           count=1, flags=re.DOTALL)
        else:
            # Sin notas → eliminar sección
            nuevo = re.sub(patron, "", contenido, count=1, flags=re.DOTALL)
        ruta.write_text(nuevo, encoding="utf-8")
        return

    # No existe la sección → solo insertar si hay contenido
    if not bloque.strip():
        return

    # Buscar dónde insertar:
    # Después del frontmatter (si existe) y antes del primer "## HH:MM"
    # Estrategia: insertar antes del primer "## " que no sea un titulo de sección de la bitácora
    # Más simple: insertar después del header H1 ("# Bitácora — ...") y antes de la primera entrada
    m_h1 = re.search(r"^#\s+Bitácora\s+—\s+.+$", contenido, re.MULTILINE)
    if m_h1:
        # Buscar el siguiente "---" después del H1 (separador de bienvenida)
        idx = m_h1.end()
        m_sep = re.search(r"\n---\n", contenido[idx:])
        if m_sep:
            insert_pos = idx + m_sep.end()
            nuevo = (
                contenido[:insert_pos]
                + "\n" + bloque_completo + "\n"
                + contenido[insert_pos:]
            )
            ruta.write_text(nuevo, encoding="utf-8")
            return

    # Fallback: insertar al inicio del archivo
    nuevo = bloque_completo + "\n" + contenido
    ruta.write_text(nuevo, encoding="utf-8")


def regenerar_seccion_destacada(ruta: Path = None) -> bool:
    """
    Reescribe la sección destacada de la bitácora del día consolidando
    todas las notas estructuradas que tenga.
    """
    try:
        if ruta is None:
            ruta = obtener_ruta_bitacora()
        if not ruta.exists():
            return False

        contenido = ruta.read_text(encoding="utf-8")

        # IMPORTANTE: excluir la sección destacada existente para no contar
        # las mismas notas dos veces (una desde la entrada original y otra
        # desde la sección destacada que las consolida).
        contenido_sin_destacado = re.sub(
            re.escape(_MARKER_DESTACADO_INI) + r".*?" + re.escape(_MARKER_DESTACADO_FIN),
            "",
            contenido,
            count=1,
            flags=re.DOTALL,
        )

        notas = _extraer_notas_estructuradas_del_md(contenido_sin_destacado)
        bloque = _construir_seccion_destacada(notas)
        _insertar_seccion_destacada(ruta, bloque)

        if notas:
            print(f"[Bitácora] Sección destacada actualizada: {len(notas)} notas")
        return True
    except Exception as e:
        print(f"[Bitácora] Error al regenerar sección destacada: {e}")
        return False


# ===========================================================================
# Fase 5d: Registro de objetos, conceptos y personas
# ===========================================================================
# Tres archivos editables manualmente vía prefijos @objeto, @diccionario,
# @persona desde el campo de notas:
#
#   - bitacoras/objetos.md          ← @objeto:      tablas / objetos del trabajo
#   - bitacoras/diccionario_datos.md ← @diccionario: conceptos / términos
#   - bitacoras/personas.md         ← @persona:     personas (complementa
#                                                    config.personas_conocidas)
#
# Cada archivo se llena solo con lo que el usuario agregue manualmente.
# No hay autogeneración a partir del contenido de bitácoras o snippets.
# ---------------------------------------------------------------------------


def _ruta_objetos() -> Path:
    """Retorna la ruta del archivo Task/objetos.md"""
    return ruta_task() / "objetos.md"


def _ruta_diccionario_datos() -> Path:
    """Retorna la ruta del archivo Task/diccionario_datos.md"""
    return ruta_task() / "diccionario_datos.md"


def _ruta_personas() -> Path:
    """Retorna la ruta del archivo Task/personas.md"""
    return ruta_task() / "personas.md"


def _procesar_entrada_estructurada(contenido: str) -> tuple:
    """
    Parsea el contenido de una nota tipo @objeto, @diccionario o @persona.
    Acepta separador ' - ' (espacio-guion-espacio) o ':' al inicio de la
    descripción.

    Formatos aceptados:
        "SGBSTDN"                              → ("SGBSTDN", "")
        "SGBSTDN - tabla maestra"              → ("SGBSTDN", "tabla maestra")
        "María López - líder funcional"      → ("María López", "líder funcional")
        "RUT - número único de identificación" → ("RUT", "número único...")

    Retorna (nombre, descripcion). Si no hay nombre válido, (None, None).
    """
    if not contenido or not contenido.strip():
        return (None, None)

    texto = contenido.strip()

    # Separador preferente: ' - ' (espacio-guion-espacio) en la primera línea
    m = re.match(r"^(.+?)\s+-\s+(.+)$", texto, re.DOTALL)
    if m:
        nombre = m.group(1).strip()
        descripcion = m.group(2).strip()
    else:
        # Separador alternativo: ':' (solo si no es parte de un wikilink)
        m2 = re.match(r"^([^:\n]+?)\s*:\s*(.+)$", texto, re.DOTALL)
        if m2:
            nombre = m2.group(1).strip()
            descripcion = m2.group(2).strip()
        else:
            # Sin separador: solo nombre (primera línea)
            nombre = texto.split("\n")[0].strip()
            descripcion = ""

    if not nombre:
        return (None, None)

    return (nombre, descripcion)


# Cabeceras y configuración por tipo de archivo
_CABECERAS_REGISTRO = {
    "objetos": {
        "tipo_yaml": "registro-objetos",
        "h1": "📚 Objetos",
        "intro": (
            "> Registro de objetos del trabajo (tablas, vistas, archivos, etc.).\n"
            "> Para agregar: escribe `@objeto: NOMBRE - descripción` en el campo de notas."
        ),
        "campo_total": "total_objetos",
        "tags": "[registro, objetos]",
    },
    "diccionario": {
        "tipo_yaml": "diccionario-datos",
        "h1": "📖 Diccionario de Datos",
        "intro": (
            "> Conceptos, términos y definiciones del dominio.\n"
            "> Para agregar: escribe `@diccionario: CONCEPTO - descripción` en el campo de notas."
        ),
        "campo_total": "total_conceptos",
        "tags": "[registro, diccionario, datos]",
    },
    "personas": {
        "tipo_yaml": "registro-personas",
        "h1": "👤 Personas",
        "intro": (
            "> Personas con las que trabajas (complementa `personas_conocidas` del config).\n"
            "> Para agregar: escribe `@persona: NOMBRE - descripción` en el campo de notas."
        ),
        "campo_total": "total_personas",
        "tags": "[registro, personas]",
    },
}


def _leer_entradas_registro(ruta: Path) -> dict:
    """
    Parsea un archivo de registro y retorna un dict ordenado por nombre:
    {
        "NOMBRE": {
            "descripcion": "...",
            "agregado": "2026-05-09",
            "bitacora_origen": "bitacora_2026-05-09",
        }
    }
    Si el archivo no existe, retorna dict vacío.
    """
    if not ruta.exists():
        return {}

    try:
        contenido = ruta.read_text(encoding="utf-8")
    except Exception:
        return {}

    entradas = {}
    bloques = re.split(r"^##\s+", contenido, flags=re.MULTILINE)
    # bloques[0] = preámbulo (frontmatter + intro), saltarlo
    for bloque in bloques[1:]:
        if not bloque.strip():
            continue
        lineas = bloque.split("\n", 1)
        nombre = lineas[0].strip()
        cuerpo = lineas[1] if len(lineas) > 1 else ""

        if not nombre:
            continue

        # Extraer campos
        descripcion = ""
        agregado = ""
        bitacora_origen = ""

        m_desc = re.search(r"-\s+📝\s+\*\*Descripción:\*\*\s*(.+?)(?=\n-\s+|\n\n|\Z)",
                           cuerpo, re.DOTALL)
        if m_desc:
            descripcion = m_desc.group(1).strip()

        m_ag = re.search(r"-\s+📅\s+\*\*Agregado:\*\*\s*(\S+)", cuerpo)
        if m_ag:
            agregado = m_ag.group(1).strip()

        m_bit = re.search(r"-\s+🔗\s+\*\*Bitácora origen:\*\*\s*\[\[([^\]]+)\]\]", cuerpo)
        if m_bit:
            bitacora_origen = m_bit.group(1).strip()

        entradas[nombre] = {
            "descripcion": descripcion,
            "agregado": agregado,
            "bitacora_origen": bitacora_origen,
        }

    return entradas


def _escribir_archivo_registro(ruta: Path, entradas: dict, tipo_archivo: str):
    """
    Escribe un archivo de registro completo (frontmatter + cabecera + entradas).
    Las entradas se ordenan alfabéticamente.
    """
    cab = _CABECERAS_REGISTRO[tipo_archivo]
    ahora = datetime.now()
    fecha_str = ahora.strftime("%Y-%m-%d")

    lineas = [
        "---",
        f"tipo: {cab['tipo_yaml']}",
        f"ultima_actualizacion: {fecha_str}",
        f"{cab['campo_total']}: {len(entradas)}",
        f"tags: {cab['tags']}",
        "---",
        "",
        f"# {cab['h1']}",
        "",
        cab["intro"],
        "",
        "---",
        "",
    ]

    if not entradas:
        lineas.append("_Sin entradas aún_")
        lineas.append("")
    else:
        for nombre in sorted(entradas.keys(), key=lambda s: s.lower()):
            datos = entradas[nombre]
            desc = datos.get("descripcion", "").strip()
            agregado = datos.get("agregado", "").strip()
            bitacora = datos.get("bitacora_origen", "").strip()

            lineas.append(f"## {nombre}")
            if desc:
                lineas.append(f"- 📝 **Descripción:** {desc}")
            else:
                lineas.append(f"- 📝 **Descripción:** _Sin descripción_")
            if agregado:
                lineas.append(f"- 📅 **Agregado:** {agregado}")
            if bitacora:
                lineas.append(f"- 🔗 **Bitácora origen:** [[{bitacora}]]")
            lineas.append("")

    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _agregar_a_registro(tipo_archivo: str, nombre: str, descripcion: str = "") -> bool:
    """
    Lógica genérica de upsert sobre un archivo de registro.

    Comportamiento de duplicados:
    - Si el nombre no existe → se agrega.
    - Si ya existe y se entrega una descripción nueva → se actualiza (descripción
      + fecha 'agregado' + bitácora origen).
    - Si ya existe y NO se entrega descripción → se preserva la existente.
    """
    if not nombre:
        return False

    if tipo_archivo == "objetos":
        ruta = _ruta_objetos()
    elif tipo_archivo == "diccionario":
        ruta = _ruta_diccionario_datos()
    elif tipo_archivo == "personas":
        ruta = _ruta_personas()
    else:
        return False

    try:
        ahora = datetime.now()
        fecha_str = ahora.strftime("%Y-%m-%d")
        bitacora_origen = f"bitacora_{fecha_str}"

        entradas = _leer_entradas_registro(ruta)
        existente = entradas.get(nombre)

        if existente is None:
            # Nueva entrada
            entradas[nombre] = {
                "descripcion": descripcion,
                "agregado": fecha_str,
                "bitacora_origen": bitacora_origen,
            }
            print(f"[Bitácora] @{tipo_archivo}: '{nombre}' agregado")
        else:
            # Entrada existente
            if descripcion:
                # Hay descripción nueva → actualizar
                entradas[nombre] = {
                    "descripcion": descripcion,
                    "agregado": fecha_str,
                    "bitacora_origen": bitacora_origen,
                }
                print(f"[Bitácora] @{tipo_archivo}: '{nombre}' actualizado")
            else:
                # Sin descripción nueva → preservar
                print(f"[Bitácora] @{tipo_archivo}: '{nombre}' ya existía — preservado")

        _escribir_archivo_registro(ruta, entradas, tipo_archivo)
        return True

    except Exception as e:
        print(f"[Bitácora] Error al agregar a {tipo_archivo} '{nombre}': {e}")
        return False


# Wrappers públicos por claridad de intención
def agregar_objeto_a_md(nombre: str, descripcion: str = "") -> bool:
    """Agrega o actualiza un objeto en bitacoras/objetos.md"""
    return _agregar_a_registro("objetos", nombre, descripcion)


def agregar_concepto_a_diccionario(concepto: str, descripcion: str = "") -> bool:
    """Agrega o actualiza un concepto en bitacoras/diccionario_datos.md"""
    return _agregar_a_registro("diccionario", concepto, descripcion)


def agregar_persona_a_md(nombre: str, descripcion: str = "") -> bool:
    """Agrega o actualiza una persona en bitacoras/personas.md"""
    return _agregar_a_registro("personas", nombre, descripcion)


# ===========================================================================
# Fase 6: Archivos agregados por tipo de task
# ===========================================================================
# Cada vez que el usuario registra @decision/@tarea/@acuerdo/@idea/
# @bloqueado/@ticket/@pendiente, la entrada se acumula en su archivo
# agregado (bitacoras/decisiones.md, bitacoras/tareas.md, etc.) además
# de escribirse en la bitácora del día.
#
# Formato del archivo agregado (Opción A — cronológico por día):
#
#     ---
#     tipo: registro-tareas
#     ultima_actualizacion: 2026-05-10
#     tags: [registro, tareas]
#     ---
#
#     # ⏳ Tareas
#
#     > Registro de todas las tareas detectadas en bitácoras.
#
#     ## 2026-05-10
#     - ⏳ revisar query de matrículas — [[bitacora_2026-05-10]]
#     - ⏳ subir reporte a SharePoint — [[bitacora_2026-05-10]]
#
#     ## 2026-05-09
#     - ⏳ validar Maestro Mallas — [[bitacora_2026-05-09]]
#
# Las secciones de día se ordenan cronológicamente descendente (hoy arriba).
# No se hace upsert: cada @tarea es una entrada nueva aunque el texto
# coincida con otra previa.
# ---------------------------------------------------------------------------


def _ruta_archivo_task(tipo: str) -> Path:
    """Retorna la ruta del archivo agregado para un tipo de task."""
    nombre_archivo = _ARCHIVOS_TASK[tipo][0]
    return ruta_task() / nombre_archivo


def _crear_archivo_task_vacio(ruta: Path, tipo: str) -> str:
    """
    Genera el contenido inicial del archivo agregado de tasks (sin entradas).
    Frontmatter + cabecera + intro. Sin secciones de día aún.
    """
    _, h1, tipo_yaml = _ARCHIVOS_TASK[tipo]
    fecha_str = datetime.now().strftime("%Y-%m-%d")
    nombre_plural = h1.split(" ", 1)[1].lower()  # "Decisiones" -> "decisiones"
    return (
        "---\n"
        f"tipo: {tipo_yaml}\n"
        f"ultima_actualizacion: {fecha_str}\n"
        f"tags: [registro, {tipo}]\n"
        "---\n"
        "\n"
        f"# {h1}\n"
        "\n"
        f"> Registro cronológico de {nombre_plural} detectadas en bitácoras.\n"
        f"> Se agrega automáticamente al usar el prefijo `@{tipo}:` en notas.\n"
        "\n"
        "---\n"
        "\n"
    )


def _actualizar_frontmatter_ultima(contenido: str, fecha_str: str) -> str:
    """
    Reemplaza el valor de `ultima_actualizacion:` en el frontmatter del
    archivo. Si no existe el campo, devuelve el contenido sin cambios.
    """
    return re.sub(
        r"^(ultima_actualizacion:\s*)\S+",
        rf"\g<1>{fecha_str}",
        contenido,
        count=1,
        flags=re.MULTILINE,
    )


def agregar_task_a_archivo(tipo: str, texto: str) -> bool:
    """
    Agrega una entrada al archivo agregado del tipo de task.

    Comportamiento:
    - Si el archivo no existe → lo crea con cabecera.
    - Si ya existe la sección de hoy (## YYYY-MM-DD) → agrega la línea al
      final de esa sección (orden cronológico de inserción).
    - Si no existe la sección de hoy → la inserta como primera (más reciente
      arriba).
    - No hace upsert: cada llamada agrega una nueva línea, aunque el texto
      sea idéntico a una previa.

    Args:
        tipo: clave de _ARCHIVOS_TASK (decision, tarea, acuerdo, idea,
              bloqueado, ticket, pendiente).
        texto: contenido literal de la entrada (lo que el usuario escribió
               después de "@tipo: ").

    Returns:
        True si se escribió correctamente, False si hubo error.
    """
    if tipo not in _ARCHIVOS_TASK:
        return False

    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return False

    try:
        ruta = _ruta_archivo_task(tipo)
        ruta.parent.mkdir(parents=True, exist_ok=True)

        fecha_str = datetime.now().strftime("%Y-%m-%d")
        emoji = _TIPOS_NOTA_ESTRUCTURADA[tipo]["emoji"]
        linea_nueva = f"- {emoji} {texto_limpio} — [[bitacora_{fecha_str}]]"
        seccion_hoy = f"## {fecha_str}"

        if not ruta.exists():
            # Crear archivo desde cero con la primera entrada del día
            base = _crear_archivo_task_vacio(ruta, tipo)
            contenido_final = base + seccion_hoy + "\n" + linea_nueva + "\n"
            ruta.write_text(contenido_final, encoding="utf-8")
            print(f"[Bitácora] @{tipo}: archivo creado y entrada agregada")
            return True

        # Archivo ya existe: leer, decidir dónde insertar
        contenido = ruta.read_text(encoding="utf-8")

        if seccion_hoy in contenido:
            # Hay sección de hoy: insertar la línea al final de ese bloque
            # Patrón: capturamos la sección de hoy hasta la próxima ## o fin
            patron = re.compile(
                r"(" + re.escape(seccion_hoy) + r".*?)(?=^## |\Z)",
                flags=re.DOTALL | re.MULTILINE,
            )
            def _append_linea(m):
                bloque = m.group(1).rstrip()
                return bloque + "\n" + linea_nueva + "\n\n"
            contenido_nuevo = patron.sub(_append_linea, contenido, count=1)
        else:
            # No hay sección de hoy: insertarla al inicio (después del
            # separador `---` que sigue al frontmatter+cabecera). Si por
            # alguna razón no hay separador, la pegamos al final del
            # preámbulo, antes de las demás secciones.
            bloque_nuevo = seccion_hoy + "\n" + linea_nueva + "\n\n"
            # Buscar la primera línea "## YYYY-..." (sección de día existente)
            m_primera_seccion = re.search(
                r"^## \d{4}-\d{2}-\d{2}", contenido, flags=re.MULTILINE
            )
            if m_primera_seccion:
                idx = m_primera_seccion.start()
                contenido_nuevo = (
                    contenido[:idx].rstrip() + "\n\n" + bloque_nuevo + contenido[idx:]
                )
            else:
                # No hay secciones de día aún: agregar al final
                contenido_nuevo = contenido.rstrip() + "\n\n" + bloque_nuevo

        # Actualizar campo ultima_actualizacion en el frontmatter
        contenido_nuevo = _actualizar_frontmatter_ultima(contenido_nuevo, fecha_str)

        ruta.write_text(contenido_nuevo, encoding="utf-8")
        print(f"[Bitácora] @{tipo}: entrada agregada en {ruta.name}")
        return True

    except Exception as e:
        print(f"[Bitácora] Error al agregar @{tipo} a archivo: {e}")
        return False
