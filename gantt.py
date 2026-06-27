"""
gantt.py
Gestiona el seguimiento de proyectos tipo Gantt.
- Clasifica actividades en proyectos usando Claude Haiku (texto, sin Vision)
- Genera diagrama Mermaid en gantt_proyectos.md
- Verifica alertas de inactividad al iniciar el agente
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta

from utils import cargar_config, ruta_proyectos
from cliente_ia import get_cliente


# ---------------------------------------------------------------------------
# Helpers de configuración y persistencia
# ---------------------------------------------------------------------------

def _ruta_gantt_data() -> Path:
    return ruta_proyectos() / "gantt_data.json"


def _ruta_gantt_md() -> Path:
    return ruta_proyectos() / "gantt_proyectos.md"


def cargar_gantt_data() -> dict:
    """Carga o inicializa el archivo de datos del Gantt."""
    ruta = _ruta_gantt_data()
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return {"proyectos": {}}  # {nombre: {fecha: minutos}}


def guardar_gantt_data(data: dict):
    with open(_ruta_gantt_data(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Gestión de proyectos en config.json
# ---------------------------------------------------------------------------

def obtener_proyectos() -> list:
    """Retorna lista de proyectos activos desde config.json."""
    config = cargar_config()
    return [p for p in config.get("proyectos", []) if p.get("estado") == "activo"]


def guardar_proyectos(proyectos: list):
    """Actualiza la lista completa de proyectos en config.json."""
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, encoding="utf-8") as f:
        config = json.load(f)
    config["proyectos"] = proyectos
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# Temperatura por defecto para clasificación (baja = determinista)
TEMPERATURA_DEFAULT = 0.2


def obtener_descripcion(proyecto: dict) -> str:
    """
    Retorna la descripción del proyecto.
    Fallback a `palabras_clave` para retrocompatibilidad con proyectos viejos.
    """
    desc = proyecto.get("descripcion", "")
    if desc:
        return desc
    # Fallback legacy
    return proyecto.get("palabras_clave", "")


def obtener_objetivos(proyecto: dict) -> str:
    """
    Retorna los objetivos específicos del proyecto.
    Si no existen, retorna string vacío (los proyectos viejos no tienen).
    """
    return proyecto.get("objetivos", "")


def obtener_temperatura(proyecto: dict) -> float:
    """
    Retorna la temperatura de clasificación del proyecto.
    Si no existe o es inválida (incluido NaN/infinito), retorna el default.
    """
    import math
    try:
        t = float(proyecto.get("temperatura", TEMPERATURA_DEFAULT))
        # NaN e infinito son floats válidos pero no sirven como temperatura
        if not math.isfinite(t):
            return TEMPERATURA_DEFAULT
        return max(0.0, min(1.0, t))
    except (TypeError, ValueError):
        return TEMPERATURA_DEFAULT


def agregar_proyecto(nombre: str, descripcion: str = "",
                     objetivos: str = "",
                     temperatura: float = TEMPERATURA_DEFAULT) -> dict:
    """
    Agrega un nuevo proyecto al config.json con la estructura ampliada:
    título, descripción general, objetivos específicos y temperatura
    de clasificación.
    """
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, encoding="utf-8") as f:
        config = json.load(f)
    nuevo = {
        "nombre": nombre.strip(),
        "descripcion": descripcion.strip(),
        "objetivos": objetivos.strip(),
        "temperatura": float(temperatura),
        "inicio": datetime.now().strftime("%Y-%m-%d"),
        "fin": None,
        "estado": "activo"
    }
    config.setdefault("proyectos", []).append(nuevo)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return nuevo


def editar_proyecto(indice: int, nombre: str, descripcion: str,
                    objetivos: str, temperatura: float, estado: str):
    """
    Edita un proyecto existente por índice.

    Comportamiento del campo `fin`:
    - Al cerrar (estado="cerrado") sin fecha previa de cierre → se setea con hoy.
    - Al reactivar (estado="activo") → se limpia (None), porque la fecha de
      cierre histórica ya no aplica si el proyecto vuelve a estar vivo.

    Si el proyecto tenía el campo legacy `palabras_clave`, se elimina al
    guardar (ya migró a `descripcion`).
    """
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, encoding="utf-8") as f:
        config = json.load(f)
    proyecto = config["proyectos"][indice]
    proyecto["nombre"] = nombre.strip()
    proyecto["descripcion"] = descripcion.strip()
    proyecto["objetivos"] = objetivos.strip()
    proyecto["temperatura"] = max(0.0, min(1.0, float(temperatura)))
    proyecto["estado"] = estado
    # Limpieza del campo legacy si existía
    if "palabras_clave" in proyecto:
        del proyecto["palabras_clave"]
    if estado == "cerrado" and not proyecto.get("fin"):
        proyecto["fin"] = datetime.now().strftime("%Y-%m-%d")
    elif estado == "activo":
        # Reactivación: limpiar fecha de fin (si existía)
        proyecto["fin"] = None
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Clasificación de actividad con el modelo rápido del proveedor
# ---------------------------------------------------------------------------

# Placeholders obligatorios en el template del prompt. Si alguno falta, el
# prompt no puede funcionar y debe rechazarse.
PLACEHOLDERS_CLASIFICACION = [
    "titulo_ventana",
    "descripcion_actividad",
    "lista_proyectos",
    "lista_nombres",
]

# Template por defecto del prompt de clasificación. El usuario puede
# sobrescribirlo desde la ventana de configuraciones (clave
# `prompt_clasificacion` en config.json).
PROMPT_CLASIFICACION_DEFAULT = """Tienes esta actividad laboral detectada en pantalla:

Ventana activa: {titulo_ventana}
Descripción de la actividad: {descripcion_actividad}

Estos son los proyectos activos del usuario, cada uno con su descripción
general y sus objetivos específicos:

{lista_proyectos}

TAREA: Determina a qué proyecto pertenece la actividad detectada.

CRITERIO DE DECISIÓN (estricto):
- La actividad debe contribuir directamente a los OBJETIVOS ESPECÍFICOS
  de un proyecto. La sola coincidencia de tecnologías, herramientas o
  palabras genéricas NO es suficiente para clasificar.
- Si la actividad NO contribuye claramente a los objetivos de ningún
  proyecto, responde "ninguno". Es preferible "ninguno" antes que un
  match dudoso.
- Si la actividad encaja parcialmente con varios proyectos, elige el
  que mejor cumpla los objetivos específicos.

RESPUESTA: SOLO el nombre exacto del proyecto de la lista ({lista_nombres})
o la palabra "ninguno". Sin explicaciones, sin comillas, sin markdown."""


def validar_prompt_clasificacion(template: str) -> tuple[bool, list[str]]:
    """
    Valida que un template de prompt contenga TODOS los placeholders
    críticos requeridos por la lógica de clasificación.

    Args:
        template: el string del template a validar.

    Returns:
        (es_valido, faltantes):
        - es_valido: True si están todos los placeholders.
        - faltantes: lista de nombres de placeholders faltantes (vacía si OK).
    """
    if not template or not isinstance(template, str):
        return False, list(PLACEHOLDERS_CLASIFICACION)

    faltantes = [
        ph for ph in PLACEHOLDERS_CLASIFICACION
        if "{" + ph + "}" not in template
    ]
    return (len(faltantes) == 0, faltantes)


def cargar_prompt_clasificacion() -> str:
    """
    Carga el template del prompt de clasificación desde config.json.
    Si la clave no existe, está vacía o tiene un template inválido,
    retorna el template por defecto.
    """
    try:
        config = cargar_config()
        custom = (config.get("prompt_clasificacion") or "").strip()
        if not custom:
            return PROMPT_CLASIFICACION_DEFAULT

        valido, _ = validar_prompt_clasificacion(custom)
        if not valido:
            print("[Gantt] ⚠ prompt_clasificacion inválido en config — usando default")
            return PROMPT_CLASIFICACION_DEFAULT
        return custom
    except Exception as e:
        print(f"[Gantt] Error leyendo prompt_clasificacion: {e} — usando default")
        return PROMPT_CLASIFICACION_DEFAULT


def clasificar_actividad(titulo_ventana: str, descripcion_actividad: str, duracion_min: int) -> str | None:
    """
    Usa el modelo rápido del proveedor para determinar a qué proyecto
    pertenece una actividad.

    El prompt se construye con tres bloques por proyecto:
      - TÍTULO: nombre identificador
      - DESCRIPCIÓN: qué es el proyecto (contexto)
      - OBJETIVOS: qué actividades cuentan como parte del proyecto

    El template del prompt se lee desde config.json (clave
    `prompt_clasificacion`). Si no existe o es inválido, se usa el
    PROMPT_CLASIFICACION_DEFAULT hardcoded.

    La temperatura usada en la llamada al LLM es el promedio de las
    temperaturas configuradas por proyecto (cada proyecto puede tener
    una). Si ninguno la define, se usa TEMPERATURA_DEFAULT.

    Skippea entradas de menos de 2 minutos.

    Returns:
        Nombre exacto del proyecto, o None si no corresponde a ninguno.
    """
    if duracion_min < 2:
        return None

    proyectos = obtener_proyectos()
    if not proyectos:
        return None

    # Construir bloques estructurados por proyecto
    bloques = []
    temperaturas = []
    for idx, p in enumerate(proyectos, 1):
        nombre_p = p["nombre"]
        descripcion = obtener_descripcion(p).strip() or "(sin descripción)"
        objetivos = obtener_objetivos(p).strip() or "(sin objetivos específicos)"
        temperaturas.append(obtener_temperatura(p))

        bloques.append(
            f"### Proyecto {idx}: {nombre_p}\n"
            f"DESCRIPCIÓN: {descripcion}\n"
            f"OBJETIVOS ESPECÍFICOS: {objetivos}"
        )

    lista_proyectos_str = "\n\n".join(bloques)
    nombres_validos = [p["nombre"] for p in proyectos]
    lista_nombres = " | ".join(f'"{n}"' for n in nombres_validos)

    # Temperatura efectiva: promedio de las configuradas (o default si lista vacía)
    temperatura_efectiva = (
        sum(temperaturas) / len(temperaturas) if temperaturas else TEMPERATURA_DEFAULT
    )

    # Cargar template (custom desde config, o default si no es válido)
    template = cargar_prompt_clasificacion()

    # Rellenar placeholders. Si .format() falla (ej. llaves accidentales
    # en el template del usuario), caemos al default sin reventar.
    try:
        prompt = template.format(
            titulo_ventana=titulo_ventana[:120],
            descripcion_actividad=descripcion_actividad[:300],
            lista_proyectos=lista_proyectos_str,
            lista_nombres=lista_nombres,
        )
    except (KeyError, IndexError, ValueError) as e:
        print(f"[Gantt] ⚠ Error formateando prompt custom: {e} — usando default")
        prompt = PROMPT_CLASIFICACION_DEFAULT.format(
            titulo_ventana=titulo_ventana[:120],
            descripcion_actividad=descripcion_actividad[:300],
            lista_proyectos=lista_proyectos_str,
            lista_nombres=lista_nombres,
        )

    try:
        cliente = get_cliente()
        resultado = cliente.clasificar(
            prompt,
            max_tokens=40,
            tipo_operacion="clasificacion_proyecto",
            temperature=temperatura_efectiva,
        )
        # Limpiar comillas o markdown que algunos modelos agregan
        resultado = resultado.strip().strip('"').strip("'").strip()
        # Verificar que sea un proyecto válido
        if resultado in nombres_validos:
            return resultado
        return None
    except Exception as e:
        print(f"[Gantt] Error clasificando actividad: {e}")
        return None


# ---------------------------------------------------------------------------
# Actualización del Gantt
# ---------------------------------------------------------------------------

def actualizar_gantt(titulo_ventana: str, descripcion: str, duracion_min: int,
                     entrada_md: str = "") -> str | None:
    """
    Clasifica la actividad y suma el tiempo al proyecto correspondiente.
    Si hay match: actualiza Gantt global, .md del proyecto y su Gantt individual.

    Args:
        entrada_md: bloque markdown completo de la entrada (cabecera + metadata + duración)
                    para escribir en el .md del proyecto.

    Returns:
        Nombre del proyecto si hubo match, None si no.
    """
    proyecto = clasificar_actividad(titulo_ventana, descripcion, duracion_min)
    if not proyecto:
        return None

    data = cargar_gantt_data()
    fecha = datetime.now().strftime("%Y-%m-%d")

    if proyecto not in data["proyectos"]:
        data["proyectos"][proyecto] = {}

    data["proyectos"][proyecto][fecha] = (
        data["proyectos"][proyecto].get(fecha, 0) + duracion_min
    )

    guardar_gantt_data(data)
    generar_mermaid()

    # Escribir también en el .md del proyecto y regenerar su Gantt individual
    if entrada_md:
        try:
            from proyectos import agregar_entrada_a_proyecto, regenerar_gantt_individual, crear_md_proyecto
            crear_md_proyecto(proyecto)
            agregar_entrada_a_proyecto(proyecto, fecha, entrada_md)
            regenerar_gantt_individual(proyecto)
        except Exception as e:
            print(f"[Gantt] Error actualizando .md del proyecto: {e}")

    print(f"[Gantt] +{duracion_min}min → {proyecto}")
    return proyecto


# ---------------------------------------------------------------------------
# Generación del diagrama Mermaid
# ---------------------------------------------------------------------------

def generar_mermaid():
    """Genera o actualiza gantt_proyectos.md con el diagrama Mermaid."""
    data  = cargar_gantt_data()
    config = cargar_config()

    if not data["proyectos"]:
        return

    # Recopilar rango de fechas (últimos 30 días con actividad)
    todas_fechas = set()
    for fechas in data["proyectos"].values():
        todas_fechas.update(fechas.keys())

    if not todas_fechas:
        return

    fecha_min = min(todas_fechas)
    fecha_max = max(todas_fechas)
    hoy = datetime.now().strftime("%Y-%m-%d")
    if fecha_max < hoy:
        fecha_max = hoy

    # Construir secciones Mermaid
    secciones = []
    for nombre_proyecto, fechas in data["proyectos"].items():
        if not fechas:
            continue

        # Encontrar rangos continuos de actividad
        dias_activos = sorted(fechas.keys())
        rangos = _agrupar_rangos(dias_activos)

        lineas_proyecto = [f"    section {nombre_proyecto}"]
        for inicio_rango, fin_rango in rangos:
            inicio_dt = datetime.strptime(inicio_rango, "%Y-%m-%d")
            fin_dt    = datetime.strptime(fin_rango, "%Y-%m-%d")
            duracion_dias = max(1, (fin_dt - inicio_dt).days + 1)
            minutos_total = sum(fechas.get(d, 0) for d in dias_activos
                               if inicio_rango <= d <= fin_rango)
            horas = minutos_total // 60
            mins  = minutos_total % 60
            label = f"{nombre_proyecto} ({horas}h {mins}m)"
            lineas_proyecto.append(
                f"    {label} :done, {inicio_rango}, {duracion_dias}d"
            )
        secciones.extend(lineas_proyecto)

    mermaid_body = "\n".join(secciones)
    fecha_generacion = datetime.now().strftime("%Y-%m-%d %H:%M")

    contenido = f"""# 📊 Gantt de Proyectos
> Actualizado automáticamente por Agente LLM - El Egypcio — {fecha_generacion}

```mermaid
gantt
    title Seguimiento de Proyectos
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
{mermaid_body}
```

---

## ⏱ Resumen de tiempo por proyecto

| Proyecto | Total horas |
|---|---|
""" + _tabla_resumen(data) + "\n"

    _ruta_gantt_md().write_text(contenido, encoding="utf-8")
    print(f"[Gantt] Mermaid actualizado: {_ruta_gantt_md().name}")


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


def _tabla_resumen(data: dict) -> str:
    filas = []
    for nombre, fechas in data["proyectos"].items():
        total_min = sum(fechas.values())
        horas = total_min // 60
        mins  = total_min % 60
        # Wikilink al .md del proyecto (slugified)
        slug = re.sub(r"\s+", "_", nombre.strip())
        slug = re.sub(r"[^\w\-]", "", slug, flags=re.UNICODE)
        filas.append(f"| [[{slug}\\|{nombre}]] | {horas}h {mins}m |")
    return "\n".join(filas)


# ---------------------------------------------------------------------------
# Alertas de inactividad
# ---------------------------------------------------------------------------

def verificar_alertas() -> list:
    """
    Revisa proyectos activos sin actividad hace N días.
    Retorna lista de strings con las alertas.
    """
    config   = cargar_config()
    umbral   = config.get("alertas", {}).get("inactividad_dias", 3)
    data     = cargar_gantt_data()
    hoy      = datetime.now().date()
    alertas  = []

    for proyecto in obtener_proyectos():
        nombre = proyecto["nombre"]
        fechas = data["proyectos"].get(nombre, {})

        if not fechas:
            # Proyecto nuevo sin actividad registrada aún
            inicio = datetime.strptime(proyecto["inicio"], "%Y-%m-%d").date()
            dias_sin_actividad = (hoy - inicio).days
        else:
            ultima = max(datetime.strptime(f, "%Y-%m-%d").date() for f in fechas)
            dias_sin_actividad = (hoy - ultima).days

        if dias_sin_actividad >= umbral:
            alertas.append(
                f"⚠️ **{nombre}** — sin actividad hace {dias_sin_actividad} días"
            )

    return alertas
