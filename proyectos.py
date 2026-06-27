"""
proyectos.py
Gestiona los archivos .md individuales de cada proyecto en Obsidian.
Cada proyecto tiene su propio archivo con frontmatter, Gantt Mermaid
individual y entradas agrupadas por bitácora diaria con wikilinks.
"""

import re
import json
from pathlib import Path
from datetime import datetime

from utils import cargar_config, ruta_bitacoras, ruta_snippets, ruta_proyectos


# ---------------------------------------------------------------------------
# Helpers de rutas
# ---------------------------------------------------------------------------

def _ruta_carpeta_proyectos() -> Path:
    """Retorna la carpeta donde viven los .md de proyectos (MOCs)."""
    return ruta_proyectos()


def _slugify(nombre: str) -> str:
    """
    Convierte un nombre de proyecto en un nombre de archivo válido.
    'Mi Proyecto' → 'Mi_Proyecto'
    """
    slug = re.sub(r"\s+", "_", nombre.strip())
    slug = re.sub(r"[^\w\-]", "", slug, flags=re.UNICODE)
    return slug


def ruta_md_proyecto(nombre: str) -> Path:
    """Retorna la ruta del .md de un proyecto dado su nombre."""
    return _ruta_carpeta_proyectos() / f"{_slugify(nombre)}.md"


# ---------------------------------------------------------------------------
# Creación de archivo .md de proyecto
# ---------------------------------------------------------------------------

def crear_md_proyecto(nombre: str, descripcion: str = "",
                      objetivos: str = "", inicio: str = None) -> Path:
    """
    Crea el archivo .md del proyecto si no existe.
    Si ya existe, no hace nada (preserva entradas anteriores).
    Retorna la ruta del archivo.

    El frontmatter incluye los campos estructurados (descripcion, objetivos),
    y el cuerpo del .md tiene secciones separadas para descripción general
    y objetivos específicos.
    """
    ruta = ruta_md_proyecto(nombre)
    if ruta.exists():
        return ruta

    inicio = inicio or datetime.now().strftime("%Y-%m-%d")

    # Renderizado defensivo: si vienen vacíos, mostramos un placeholder
    desc_render = descripcion.strip() if descripcion and descripcion.strip() else "_Sin descripción aún_"
    obj_render = objetivos.strip() if objetivos and objetivos.strip() else "_Sin objetivos específicos definidos_"

    # YAML multilinea seguro: si tienen saltos de línea, usamos bloque literal
    def _yaml_field(valor: str) -> str:
        if not valor:
            return '""'
        if "\n" in valor or ":" in valor:
            # Bloque literal estilo "|-"; indentar 2 espacios cada línea
            lineas = valor.split("\n")
            indentado = "\n".join("  " + l for l in lineas)
            return f"|-\n{indentado}"
        return valor

    contenido = f"""---
proyecto: {nombre}
inicio: {inicio}
fin: 
estado: activo
descripcion: {_yaml_field(descripcion)}
objetivos: {_yaml_field(objetivos)}
tags: [proyecto]
---

# 📌 {nombre}

## Descripción
{desc_render}

## 🎯 Objetivos específicos
{obj_render}

## 📊 Gantt del proyecto

```mermaid
gantt
    title {nombre}
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section {nombre}
    Sin actividad registrada :milestone, {inicio}, 1d
```

## 📅 Actividades registradas

<!-- ENTRADAS_INICIO -->
<!-- ENTRADAS_FIN -->
"""

    ruta.write_text(contenido, encoding="utf-8")
    print(f"[Proyectos] Archivo creado: {ruta.name}")
    return ruta


# ---------------------------------------------------------------------------
# Agregar entrada al .md del proyecto
# ---------------------------------------------------------------------------

def agregar_entrada_a_proyecto(nombre_proyecto: str, fecha_str: str, entrada_md: str):
    """
    Agrega una entrada al .md del proyecto, agrupada bajo el wikilink
    de la bitácora del día. Orden descendente: lo más reciente arriba.

    Si ya existe la sección del día, hace append dentro de ella (al inicio).
    Si no existe, crea la sección al inicio del bloque de entradas.
    """
    ruta = ruta_md_proyecto(nombre_proyecto)
    if not ruta.exists():
        crear_md_proyecto(nombre_proyecto)

    contenido = ruta.read_text(encoding="utf-8")
    wikilink_dia = f"### [[bitacora_{fecha_str}]]"

    if "<!-- ENTRADAS_INICIO -->" not in contenido or "<!-- ENTRADAS_FIN -->" not in contenido:
        # Archivo viejo sin marcadores — agregar al final
        nuevo_contenido = contenido + f"\n\n{wikilink_dia}\n{entrada_md}\n"
        ruta.write_text(nuevo_contenido, encoding="utf-8")
        return

    # Buscar si ya existe la sección del día
    if wikilink_dia in contenido:
        # Hacer append dentro de la sección del día (al inicio para orden desc dentro del día)
        # Insertamos justo después del título del día
        patron = re.escape(wikilink_dia) + r"\n"
        nuevo_contenido = re.sub(
            patron,
            f"{wikilink_dia}\n{entrada_md}\n",
            contenido,
            count=1
        )
    else:
        # Crear nueva sección de día al inicio del bloque de entradas
        marcador = "<!-- ENTRADAS_INICIO -->"
        nueva_seccion = f"{marcador}\n\n{wikilink_dia}\n{entrada_md}\n"
        nuevo_contenido = contenido.replace(marcador, nueva_seccion, 1)

    ruta.write_text(nuevo_contenido, encoding="utf-8")


# ---------------------------------------------------------------------------
# Regenerar Gantt individual del proyecto
# ---------------------------------------------------------------------------

def regenerar_gantt_individual(nombre_proyecto: str):
    """
    Reescribe SOLO el bloque ```mermaid``` del .md del proyecto
    con la información actualizada de gantt_data.json.
    """
    from gantt import cargar_gantt_data

    ruta = ruta_md_proyecto(nombre_proyecto)
    if not ruta.exists():
        return

    data = cargar_gantt_data()
    fechas = data.get("proyectos", {}).get(nombre_proyecto, {})

    if not fechas:
        return

    dias_activos = sorted(fechas.keys())
    rangos = _agrupar_rangos(dias_activos)

    lineas = [
        "```mermaid",
        "gantt",
        f"    title {nombre_proyecto}",
        "    dateFormat YYYY-MM-DD",
        "    axisFormat %d/%m",
        f"    section {nombre_proyecto}"
    ]

    for inicio_rango, fin_rango in rangos:
        inicio_dt = datetime.strptime(inicio_rango, "%Y-%m-%d")
        fin_dt    = datetime.strptime(fin_rango, "%Y-%m-%d")
        dias = max(1, (fin_dt - inicio_dt).days + 1)
        minutos = sum(fechas.get(d, 0) for d in dias_activos
                     if inicio_rango <= d <= fin_rango)
        horas = minutos // 60
        mins  = minutos % 60
        label = f"Trabajo ({horas}h {mins}m)"
        lineas.append(f"    {label} :done, {inicio_rango}, {dias}d")

    lineas.append("```")
    nuevo_mermaid = "\n".join(lineas)

    contenido = ruta.read_text(encoding="utf-8")
    # Reemplazar el bloque mermaid existente
    patron = r"```mermaid\n.*?```"
    contenido = re.sub(patron, nuevo_mermaid, contenido, count=1, flags=re.DOTALL)

    ruta.write_text(contenido, encoding="utf-8")


def _agrupar_rangos(dias: list) -> list:
    """Agrupa días consecutivos en rangos (inicio, fin)."""
    if not dias:
        return []
    rangos = []
    inicio = dias[0]
    anterior = dias[0]
    for dia in dias[1:]:
        actual_dt   = datetime.strptime(dia, "%Y-%m-%d")
        anterior_dt = datetime.strptime(anterior, "%Y-%m-%d")
        if (actual_dt - anterior_dt).days <= 1:
            anterior = dia
        else:
            rangos.append((inicio, anterior))
            inicio = dia
            anterior = dia
    rangos.append((inicio, anterior))
    return rangos


# ---------------------------------------------------------------------------
# Migración retroactiva de bitácoras antiguas
# ---------------------------------------------------------------------------

def migrar_bitacoras_antiguas(callback_progreso=None) -> dict:
    """
    Lee todas las bitácoras existentes, clasifica cada entrada con Claude
    contra los proyectos activos, y reconstruye los .md de proyectos.

    Args:
        callback_progreso: función opcional callback_progreso(actual, total, mensaje)

    Returns:
        dict con estadísticas: {"entradas_procesadas": N, "matches": M, ...}
    """
    from gantt import clasificar_actividad, cargar_gantt_data, guardar_gantt_data, obtener_proyectos

    config = cargar_config()
    ruta_bitacoras_dir = ruta_bitacoras()

    archivos_bitacora = sorted(ruta_bitacoras_dir.glob("bitacora_*.md"))

    proyectos_activos = obtener_proyectos()
    if not proyectos_activos:
        return {"error": "No hay proyectos activos para clasificar"}

    # Asegurar que cada proyecto tenga su .md
    # Usa los campos nuevos (descripcion, objetivos) con fallback a palabras_clave legacy
    for p in proyectos_activos:
        descripcion = p.get("descripcion", "") or p.get("palabras_clave", "")
        objetivos = p.get("objetivos", "")
        crear_md_proyecto(p["nombre"], descripcion, objetivos, p.get("inicio"))

    # Resetear data de Gantt para reconstruir desde cero
    gantt_data = cargar_gantt_data()

    stats = {
        "archivos_procesados": 0,
        "entradas_procesadas": 0,
        "matches": 0,
        "por_proyecto": {}
    }

    total = len(archivos_bitacora)
    for idx, archivo in enumerate(archivos_bitacora, 1):
        if callback_progreso:
            callback_progreso(idx, total, f"Procesando {archivo.name}...")

        fecha_match = re.match(r"bitacora_(\d{4}-\d{2}-\d{2})\.md", archivo.name)
        if not fecha_match:
            continue
        fecha_str = fecha_match.group(1)

        contenido = archivo.read_text(encoding="utf-8")
        entradas = _parsear_entradas_bitacora(contenido)

        for entrada in entradas:
            stats["entradas_procesadas"] += 1
            titulo = entrada.get("titulo_ventana", "")
            descripcion = entrada.get("actividad", "")
            duracion = entrada.get("duracion_min", 0)

            if duracion < 2:
                continue

            proyecto = clasificar_actividad(titulo, descripcion, duracion)
            if not proyecto:
                continue

            stats["matches"] += 1
            stats["por_proyecto"][proyecto] = stats["por_proyecto"].get(proyecto, 0) + 1

            # Agregar al .md del proyecto
            agregar_entrada_a_proyecto(proyecto, fecha_str, entrada["markdown_completo"])

            # Acumular en gantt_data
            if proyecto not in gantt_data["proyectos"]:
                gantt_data["proyectos"][proyecto] = {}
            gantt_data["proyectos"][proyecto][fecha_str] = (
                gantt_data["proyectos"][proyecto].get(fecha_str, 0) + duracion
            )

        stats["archivos_procesados"] += 1

    guardar_gantt_data(gantt_data)

    # Regenerar Gantt individual de cada proyecto
    for p in proyectos_activos:
        regenerar_gantt_individual(p["nombre"])

    if callback_progreso:
        callback_progreso(total, total, "Migración completada ✅")

    return stats


def _parsear_entradas_bitacora(contenido: str) -> list:
    """
    Parsea un .md de bitácora y extrae las entradas individuales.
    Cada entrada empieza con '## HH:MM | ...' y termina antes de la siguiente
    o al llegar a un separador '---'.

    Retorna lista de dicts con: titulo_ventana, actividad, duracion_min, markdown_completo
    """
    entradas = []
    # Patrón: cabecera de entrada hasta la próxima cabecera o fin
    patron = re.compile(
        r"(## \d{2}:\d{2}\s*\|.*?)(?=\n## \d{2}:\d{2}\s*\||\Z)",
        re.DOTALL
    )

    for match in patron.finditer(contenido):
        bloque = match.group(1).strip()

        # Extraer título de ventana de la cabecera
        cabecera_match = re.match(r"## \d{2}:\d{2}\s*\|\s*[^—]+—\s*(.+)", bloque)
        titulo = cabecera_match.group(1).strip() if cabecera_match else ""

        # Extraer actividad
        act_match = re.search(r"📌\s*\*\*Actividad:\*\*\s*(.+?)(?:\n|$)", bloque)
        actividad = act_match.group(1).strip() if act_match else ""

        # Extraer duración en minutos
        dur_match = re.search(r"⏱\s*\*\*Duración:\*\*\s*(\d+)\s*min", bloque)
        duracion = int(dur_match.group(1)) if dur_match else 0

        # Limpiar el separador final si existe
        markdown_limpio = re.sub(r"\n---\s*$", "", bloque).strip()

        entradas.append({
            "titulo_ventana": titulo,
            "actividad": actividad,
            "duracion_min": duracion,
            "markdown_completo": markdown_limpio
        })

    return entradas


# ---------------------------------------------------------------------------
# Listar proyectos para el popup del Gantt
# ---------------------------------------------------------------------------

def listar_proyectos_con_md() -> list:
    """
    Retorna lista de tuplas (nombre, ruta_md) para los proyectos activos
    que tengan archivo .md generado.
    """
    from gantt import obtener_proyectos
    resultado = []
    for p in obtener_proyectos():
        ruta = ruta_md_proyecto(p["nombre"])
        if ruta.exists():
            resultado.append((p["nombre"], ruta))
    return resultado


# ===========================================================================
# Fase 4: MOC ampliado por proyecto
# ===========================================================================
# Agrega al .md del proyecto: frontmatter ampliado, sección de snippets,
# sección de resumen de actividad. Todo se calcula localmente sin LLM.
#
# Marcadores usados (todo el resto del archivo se preserva intacto):
#   <!-- SNIPPETS_INICIO --> ... <!-- SNIPPETS_FIN -->
#   <!-- RESUMEN_INICIO --> ... <!-- RESUMEN_FIN -->
# ---------------------------------------------------------------------------

# Marcadores de regiones autogestionadas
_MARKER_SNIPPETS_INI = "<!-- SNIPPETS_INICIO -->"
_MARKER_SNIPPETS_FIN = "<!-- SNIPPETS_FIN -->"
_MARKER_RESUMEN_INI  = "<!-- RESUMEN_INICIO -->"
_MARKER_RESUMEN_FIN  = "<!-- RESUMEN_FIN -->"


def _slug_proyecto_para_tag(nombre: str) -> str:
    """
    Convierte un nombre de proyecto en slug para tag (sin tildes, minúsculas,
    guiones). 'Mi Proyecto' → 'mi-proyecto'.
    Reusa la misma lógica que bitacora._slug_tag para consistencia.
    """
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", nombre.strip())
    s = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _parsear_entradas_md_proyecto(contenido: str) -> list:
    """
    Parsea las entradas del .md de un proyecto extraídas bajo cada wikilink
    de bitácora. Retorna lista de dicts:
    {fecha, herramienta, actividad, duracion_min, bloque}
    """
    entradas = []

    # Cada entrada en el .md de proyecto empieza con '#### HH:MM | ...'
    # bajo una sección '### [[bitacora_YYYY-MM-DD]]'
    # Recorremos el contenido capturando fecha actual del bloque
    fecha_actual = None

    # Dividimos por líneas y vamos detectando contexto
    lineas = contenido.split("\n")
    bloque_actual = []
    en_entrada = False

    def cerrar_bloque():
        nonlocal bloque_actual, en_entrada
        if bloque_actual and en_entrada:
            texto = "\n".join(bloque_actual)
            # Extraer datos
            herr_m = re.search(r"🔧\s*\*\*Herramienta:\*\*\s*(.+)", texto)
            act_m  = re.search(r"📌\s*\*\*Actividad:\*\*\s*(.+)", texto)
            dur_m  = re.search(r"⏱\s*\*\*Duración:\*\*\s*(?:(\d+)\s*min)?\s*(\d+)?s?", texto)

            herramienta = herr_m.group(1).strip() if herr_m else ""
            # Limpiar wikilinks del campo herramienta
            m_w = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", herramienta)
            if m_w:
                herramienta = (m_w.group(2) or m_w.group(1)).strip()

            actividad = act_m.group(1).strip() if act_m else ""
            mins = int(dur_m.group(1)) if dur_m and dur_m.group(1) else 0
            segs = int(dur_m.group(2)) if dur_m and dur_m.group(2) else 0
            duracion = mins + segs / 60.0

            entradas.append({
                "fecha": fecha_actual,
                "herramienta": herramienta,
                "actividad": actividad,
                "duracion_min": duracion,
                "bloque": texto
            })
        bloque_actual = []
        en_entrada = False

    for linea in lineas:
        # ¿Es línea de fecha? "### [[bitacora_YYYY-MM-DD]]"
        m_fecha = re.match(r"###\s+\[\[bitacora_(\d{4}-\d{2}-\d{2})\]\]", linea)
        if m_fecha:
            cerrar_bloque()
            fecha_actual = m_fecha.group(1)
            continue

        # ¿Es inicio de entrada? "#### HH:MM | ..." o "## HH:MM | ..."
        if re.match(r"#{2,4}\s+\d{2}:\d{2}\s*\|", linea):
            cerrar_bloque()
            en_entrada = True
            bloque_actual = [linea]
            continue

        # ¿Es separador? "---"
        if linea.strip() == "---":
            cerrar_bloque()
            continue

        if en_entrada:
            bloque_actual.append(linea)

    cerrar_bloque()
    return entradas


def _calcular_resumen_proyecto(nombre_proyecto: str, contenido_md: str) -> dict:
    """
    Calcula métricas globales del proyecto a partir del .md existente.
    100% local, sin API.
    """
    entradas = _parsear_entradas_md_proyecto(contenido_md)

    if not entradas:
        return {
            "n_capturas": 0,
            "n_reuniones": 0,
            "horas_totales": 0.0,
            "duracion_reuniones_min": 0,
            "ultima_actividad": "",
            "personas": [],
            "herramientas": [],
            "fuentes": [],
        }

    n_capturas = len(entradas)
    n_reuniones = sum(1 for e in entradas if "🎥 Reunión" in e["bloque"])
    minutos_total = sum(e["duracion_min"] for e in entradas)
    minutos_reuniones = sum(
        e["duracion_min"] for e in entradas if "🎥 Reunión" in e["bloque"]
    )

    # Última actividad: la fecha más reciente
    fechas = [e["fecha"] for e in entradas if e["fecha"]]
    ultima = max(fechas) if fechas else ""

    # Herramientas usadas (top 10 por frecuencia)
    from collections import Counter
    cnt_herr = Counter()
    for e in entradas:
        h = e["herramienta"].strip()
        if h:
            cnt_herr[h] += 1
    herramientas = [h for h, _ in cnt_herr.most_common(10)]

    # Personas detectadas en el contenido del .md de proyecto
    cfg = cargar_config()
    personas = _detectar_personas_proyecto(contenido_md, cfg)

    # Fuentes detectadas (Banner9, Athena, etc.)
    fuentes = _detectar_fuentes_proyecto(contenido_md)

    return {
        "n_capturas": n_capturas,
        "n_reuniones": n_reuniones,
        "horas_totales": round(minutos_total / 60.0, 1),
        "duracion_reuniones_min": int(round(minutos_reuniones)),
        "ultima_actividad": ultima,
        "personas": personas,
        "herramientas": herramientas,
        "fuentes": fuentes,
    }


def _detectar_personas_proyecto(contenido: str, cfg: dict) -> list:
    """
    Detecta personas mencionadas en el .md del proyecto usando matching
    flexible (tolerante a tildes y a nombres extendidos).
    Reusa lógica similar a bitacora._detectar_personas.
    """
    import unicodedata
    def norm(t):
        nfkd = unicodedata.normalize("NFKD", t)
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

    candidatos = set()
    for nombre in cfg.get("personas_conocidas", []) or []:
        if isinstance(nombre, str) and nombre.strip():
            candidatos.add(nombre.strip())
    for p in cfg.get("proyectos", []) or []:
        # Combinar descripción + objetivos + palabras_clave (legacy)
        texto_proyecto = " ".join([
            p.get("descripcion", "") or "",
            p.get("objetivos", "") or "",
            p.get("palabras_clave", "") or "",
        ])
        for m in re.finditer(r"\b([A-ZÁ-Ú][a-zá-ú]+\s+[A-ZÁ-Ú][a-zá-ú]+)\b", texto_proyecto):
            candidatos.add(m.group(1).strip())

    contenido_norm = norm(contenido)

    personas = []
    vistas = set()
    for nombre in candidatos:
        palabras = [norm(w) for w in nombre.split() if len(w) >= 3]
        if not palabras:
            continue
        if all(re.search(r"\b" + re.escape(p) + r"\b", contenido_norm) for p in palabras):
            if nombre.lower() not in vistas:
                vistas.add(nombre.lower())
                personas.append(nombre)
    personas.sort()
    return personas


def _detectar_fuentes_proyecto(contenido: str) -> list:
    """
    Detecta fuentes/sistemas mencionados (Banner9, Athena, Smartcampus, etc.).
    Lista hardcoded similar a bitacora._MAPEO_FUENTES.
    """
    mapeo = {
        "banner9": "Banner9", "banner 9": "Banner9", "banner": "Banner9",
        "smartcampus": "Smartcampus", "smart campus": "Smartcampus",
        "aws": "AWS", "athena": "Athena",
        "confluence": "Confluence", "jira": "Jira", "uss": "USS",
    }
    contenido_lower = contenido.lower()
    encontradas = []
    vistas = set()
    for clave, canonico in mapeo.items():
        if re.search(r"\b" + re.escape(clave) + r"\b", contenido_lower):
            if canonico not in vistas:
                vistas.add(canonico)
                encontradas.append(canonico)
    return encontradas


def _listar_snippets_de_proyecto(nombre_proyecto: str) -> list:
    """
    Busca en bitacoras/snippets/ los archivos .md cuyo frontmatter
    referencia este proyecto. Retorna lista de dicts:
    {ruta_relativa, fecha, hora, lenguaje}
    Ordenada por fecha+hora descendente (más reciente primero).
    """
    config = cargar_config()
    ruta_snippets_dir = ruta_snippets()
    if not ruta_snippets_dir.exists():
        return []

    encontrados = []
    slug = _slug_proyecto_para_tag(nombre_proyecto)

    for archivo in ruta_snippets_dir.glob("*.md"):
        try:
            contenido = archivo.read_text(encoding="utf-8")
        except Exception:
            continue

        # Buscar el frontmatter
        if not contenido.startswith("---"):
            continue
        partes = contenido.split("---", 2)
        if len(partes) < 3:
            continue
        fm = partes[1]

        # ¿Este snippet pertenece al proyecto?
        # Match por: proyecto: <nombre>  o  tags: [..., proyecto/<slug>, ...]
        es_del_proyecto = False
        # Match exacto por línea "proyecto: <nombre>"
        if re.search(r"^proyecto:\s*" + re.escape(nombre_proyecto) + r"\s*$",
                     fm, re.MULTILINE):
            es_del_proyecto = True
        # Match por tag jerárquico
        if re.search(r"proyecto/" + re.escape(slug) + r"(?:[\s,\]]|$)", fm):
            es_del_proyecto = True

        if not es_del_proyecto:
            continue

        # Extraer metadata
        m_fecha = re.search(r"^fecha:\s*(\S+)", fm, re.MULTILINE)
        m_hora  = re.search(r"^hora:\s*(\S+)", fm, re.MULTILINE)
        m_leng  = re.search(r"^lenguaje:\s*(\S+)", fm, re.MULTILINE)

        encontrados.append({
            "nombre_archivo": archivo.stem,
            "fecha": m_fecha.group(1) if m_fecha else "",
            "hora":  m_hora.group(1) if m_hora else "",
            "lenguaje": m_leng.group(1) if m_leng else "?",
        })

    # Ordenar por fecha+hora descendente
    encontrados.sort(key=lambda s: (s["fecha"], s["hora"]), reverse=True)
    return encontrados


def _construir_seccion_snippets(snippets: list) -> str:
    """Genera el bloque markdown de la sección Snippets."""
    if not snippets:
        return "_Sin snippets registrados_"

    lineas = []
    for s in snippets:
        nombre = s["nombre_archivo"]
        fecha  = s["fecha"]
        hora   = s["hora"]
        leng   = s["lenguaje"].upper()
        # Wikilink al snippet (path relativo desde la raíz del vault)
        wikilink = f"[[snippets/{nombre}|{leng} — {fecha} {hora}]]"
        lineas.append(f"- 📎 {wikilink}")
    return "\n".join(lineas)


def _construir_seccion_resumen(resumen: dict) -> str:
    """Genera el bloque markdown de la sección Resumen de actividad."""
    horas = resumen.get("horas_totales", 0)
    n_cap = resumen.get("n_capturas", 0)
    n_reu = resumen.get("n_reuniones", 0)
    dur_reu = resumen.get("duracion_reuniones_min", 0)
    ult = resumen.get("ultima_actividad", "")
    personas = resumen.get("personas", [])
    herramientas = resumen.get("herramientas", [])
    fuentes = resumen.get("fuentes", [])

    lineas = []
    lineas.append(f"- ⏱ **Tiempo total:** {horas} h")
    lineas.append(f"- 📷 **N° de capturas:** {n_cap}")
    lineas.append(f"- 🎥 **N° de reuniones:** {n_reu} ({dur_reu} min)")
    if ult:
        lineas.append(f"- 📅 **Última actividad:** {ult}")

    if personas:
        personas_links = ", ".join(f"[[{p}]]" for p in personas)
        lineas.append(f"- 👥 **Personas:** {personas_links}")

    if herramientas:
        herr_links = ", ".join(f"[[{h}]]" for h in herramientas)
        lineas.append(f"- 🔧 **Herramientas:** {herr_links}")

    if fuentes:
        fuentes_links = ", ".join(f"[[{f}]]" for f in fuentes)
        lineas.append(f"- 📊 **Fuentes:** {fuentes_links}")

    return "\n".join(lineas)


def _frontmatter_ampliado(nombre_proyecto: str, fm_existente: str,
                           resumen: dict) -> str:
    """
    Toma el frontmatter existente del .md de proyecto y le agrega/actualiza
    los campos calculados. Preserva los campos que ya existen.

    fm_existente: el contenido entre los '---' (sin los delimitadores).
    Retorna el nuevo frontmatter completo (con delimitadores).
    """
    # Parsear el frontmatter existente como dict simple (línea por línea)
    campos_existentes = {}
    orden_existentes = []
    for linea in fm_existente.split("\n"):
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", linea)
        if m:
            k = m.group(1)
            v = m.group(2)
            campos_existentes[k] = v
            if k not in orden_existentes:
                orden_existentes.append(k)

    # Campos calculados que vamos a agregar/actualizar
    campos_calculados = {
        "ultima_actividad": resumen.get("ultima_actividad", ""),
        "horas_totales": resumen.get("horas_totales", 0),
        "n_capturas": resumen.get("n_capturas", 0),
        "n_reuniones": resumen.get("n_reuniones", 0),
        "n_snippets": resumen.get("n_snippets", 0),
    }

    # Listas (las formateamos como [x, y, z])
    personas = resumen.get("personas", [])
    herramientas = resumen.get("herramientas", [])
    if personas:
        campos_calculados["personas"] = "[" + ", ".join(personas) + "]"
    if herramientas:
        campos_calculados["herramientas"] = "[" + ", ".join(herramientas) + "]"

    # Construir el frontmatter en orden:
    # 1. Campos originales en su orden
    # 2. Campos calculados (que no estuvieran ya)
    lineas = ["---"]
    campos_finales = dict(campos_existentes)
    campos_finales.update(campos_calculados)

    # Mantener el orden original primero
    ya_escritos = set()
    for k in orden_existentes:
        if k in campos_finales:
            lineas.append(f"{k}: {campos_finales[k]}")
            ya_escritos.add(k)

    # Después agregar los nuevos campos calculados que no estuvieran
    for k, v in campos_calculados.items():
        if k not in ya_escritos:
            lineas.append(f"{k}: {v}")

    lineas.append("---")
    return "\n".join(lineas)


def _reemplazar_o_insertar_seccion(contenido: str, marker_ini: str,
                                    marker_fin: str, titulo_seccion: str,
                                    cuerpo: str,
                                    posicion_si_no_existe: str = "antes_actividades") -> str:
    """
    Reemplaza el contenido entre los marcadores marker_ini y marker_fin.
    Si los marcadores no existen, inserta una nueva sección con su título
    en la posición indicada:
    - 'antes_actividades': justo antes de '## 📅 Actividades registradas'
    - 'antes_entradas_marker': justo antes de '<!-- ENTRADAS_INICIO -->'

    El bloque resultante se ve así:
        ## {titulo_seccion}
        {marker_ini}
        {cuerpo}
        {marker_fin}
    """
    bloque_completo = (
        f"## {titulo_seccion}\n"
        f"{marker_ini}\n"
        f"{cuerpo}\n"
        f"{marker_fin}\n"
    )

    # Caso 1: los marcadores ya existen → reemplazar contenido entre ellos
    patron = (
        re.escape(marker_ini)
        + r".*?"
        + re.escape(marker_fin)
    )
    if re.search(patron, contenido, flags=re.DOTALL):
        nuevo = re.sub(
            patron,
            f"{marker_ini}\n{cuerpo}\n{marker_fin}",
            contenido,
            count=1,
            flags=re.DOTALL,
        )
        return nuevo

    # Caso 2: insertar nueva sección
    if posicion_si_no_existe == "antes_actividades":
        # Insertar antes del header '## 📅 Actividades registradas'
        idx_actividades = contenido.find("## 📅 Actividades registradas")
        if idx_actividades > 0:
            return contenido[:idx_actividades] + bloque_completo + "\n" + contenido[idx_actividades:]

    if posicion_si_no_existe == "antes_entradas_marker":
        idx_marker = contenido.find("<!-- ENTRADAS_INICIO -->")
        if idx_marker > 0:
            return contenido[:idx_marker] + bloque_completo + "\n" + contenido[idx_marker:]

    # Fallback: agregar al final
    return contenido + "\n" + bloque_completo


def actualizar_moc_proyecto(nombre_proyecto: str) -> bool:
    """
    Actualiza el .md del proyecto con (Fase 4):
    - Frontmatter ampliado (métricas calculadas)
    - Sección de snippets relacionados
    - Sección de resumen de actividad

    Preserva intactas:
    - La descripción del proyecto
    - El bloque Mermaid del Gantt
    - La sección de actividades registradas (con sus entradas)

    Compatible con archivos .md viejos (los migra automáticamente
    insertando solo las secciones nuevas).

    100% local, sin llamadas a LLM.
    Retorna True si tuvo éxito, False en caso contrario.
    """
    try:
        ruta = ruta_md_proyecto(nombre_proyecto)
        if not ruta.exists():
            return False

        contenido = ruta.read_text(encoding="utf-8")

        # 1. Calcular resumen del proyecto
        resumen = _calcular_resumen_proyecto(nombre_proyecto, contenido)

        # 2. Listar snippets del proyecto
        snippets = _listar_snippets_de_proyecto(nombre_proyecto)
        resumen["n_snippets"] = len(snippets)

        # 3. Construir secciones nuevas
        cuerpo_snippets = _construir_seccion_snippets(snippets)
        cuerpo_resumen = _construir_seccion_resumen(resumen)

        # 4. Reemplazar o insertar secciones (en este orden, para que aparezcan
        #    en el orden correcto en el archivo: snippets antes que resumen)

        # Sección Snippets — entre Gantt y Resumen
        contenido = _reemplazar_o_insertar_seccion(
            contenido,
            _MARKER_SNIPPETS_INI,
            _MARKER_SNIPPETS_FIN,
            "📎 Snippets",
            cuerpo_snippets,
            posicion_si_no_existe="antes_actividades",
        )

        # Sección Resumen de actividad — entre Snippets y Actividades
        contenido = _reemplazar_o_insertar_seccion(
            contenido,
            _MARKER_RESUMEN_INI,
            _MARKER_RESUMEN_FIN,
            "📈 Resumen de actividad",
            cuerpo_resumen,
            posicion_si_no_existe="antes_actividades",
        )

        # 5. Frontmatter ampliado
        if contenido.startswith("---"):
            partes = contenido.split("---", 2)
            if len(partes) >= 3:
                fm_existente = partes[1].strip("\n")
                resto = partes[2].lstrip("\n")
                fm_nuevo = _frontmatter_ampliado(
                    nombre_proyecto, fm_existente, resumen
                )
                contenido = fm_nuevo + "\n\n" + resto
        else:
            # No tiene frontmatter — agregar uno mínimo con campos calculados
            fm_nuevo = _frontmatter_ampliado(nombre_proyecto, "", resumen)
            contenido = fm_nuevo + "\n\n" + contenido

        ruta.write_text(contenido, encoding="utf-8")
        print(f"[Proyectos] MOC actualizado: {nombre_proyecto} "
              f"({resumen['horas_totales']}h, {resumen['n_capturas']} entradas, "
              f"{len(snippets)} snippets)")
        return True

    except Exception as e:
        print(f"[Proyectos] Error al actualizar MOC '{nombre_proyecto}': {e}")
        return False


def actualizar_mocs_de(nombres_proyectos: list) -> int:
    """
    Actualiza los MOCs de una lista de proyectos.
    Retorna el número de proyectos actualizados exitosamente.
    """
    ok = 0
    for nombre in nombres_proyectos:
        if actualizar_moc_proyecto(nombre):
            ok += 1
    return ok
