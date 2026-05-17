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

from utils import cargar_config
from cliente_ia import get_cliente


# ---------------------------------------------------------------------------
# Helpers de configuración y persistencia
# ---------------------------------------------------------------------------

def _ruta_gantt_data() -> Path:
    config = cargar_config()
    ruta = Path(config["ruta_base"]) / "bitacoras"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta / "gantt_data.json"


def _ruta_gantt_md() -> Path:
    config = cargar_config()
    return Path(config["ruta_base"]) / "bitacoras" / "gantt_proyectos.md"


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


def agregar_proyecto(nombre: str, palabras_clave: str) -> dict:
    """Agrega un nuevo proyecto al config.json."""
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, encoding="utf-8") as f:
        config = json.load(f)
    nuevo = {
        "nombre": nombre.strip(),
        "palabras_clave": palabras_clave.strip(),
        "inicio": datetime.now().strftime("%Y-%m-%d"),
        "fin": None,
        "estado": "activo"
    }
    config.setdefault("proyectos", []).append(nuevo)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return nuevo


def editar_proyecto(indice: int, nombre: str, palabras_clave: str, estado: str):
    """
    Edita un proyecto existente por índice.

    Comportamiento del campo `fin`:
    - Al cerrar (estado="cerrado") sin fecha previa de cierre → se setea con hoy.
    - Al reactivar (estado="activo") → se limpia (None), porque la fecha de
      cierre histórica ya no aplica si el proyecto vuelve a estar vivo.
    """
    ruta = Path(__file__).parent / "config.json"
    with open(ruta, encoding="utf-8") as f:
        config = json.load(f)
    proyecto = config["proyectos"][indice]
    proyecto["nombre"] = nombre.strip()
    proyecto["palabras_clave"] = palabras_clave.strip()
    proyecto["estado"] = estado
    if estado == "cerrado" and not proyecto.get("fin"):
        proyecto["fin"] = datetime.now().strftime("%Y-%m-%d")
    elif estado == "activo":
        # Reactivación: limpiar fecha de fin (si existía)
        proyecto["fin"] = None
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Clasificación de actividad con Claude Haiku
# ---------------------------------------------------------------------------

def clasificar_actividad(titulo_ventana: str, descripcion_actividad: str, duracion_min: int) -> str | None:
    """
    Usa Claude Haiku para determinar a qué proyecto pertenece una actividad.
    Retorna el nombre del proyecto o None si no corresponde a ninguno.
    Skippea entradas de menos de 2 minutos.
    """
    if duracion_min < 2:
        return None

    proyectos = obtener_proyectos()
    if not proyectos:
        return None

    # Construir lista de proyectos para el prompt
    lista_proyectos = "\n".join([
        f"- {p['nombre']}: {p.get('palabras_clave', '')}"
        for p in proyectos
    ])

    prompt = f"""Tienes esta actividad laboral:
Ventana: {titulo_ventana[:80]}
Descripción: {descripcion_actividad[:150]}

Proyectos activos:
{lista_proyectos}

¿A qué proyecto pertenece esta actividad?
Responde SOLO con el nombre exacto del proyecto de la lista, o "ninguno" si no corresponde a ninguno.
No expliques nada más."""

    try:
        cliente = get_cliente()
        resultado = cliente.clasificar(prompt, max_tokens=30,
                                       tipo_operacion="clasificacion_proyecto")
        # Limpiar comillas o markdown que algunos modelos agregan
        resultado = resultado.strip().strip('"').strip("'").strip()
        # Verificar que sea un proyecto válido
        nombres = [p["nombre"] for p in proyectos]
        if resultado in nombres:
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
