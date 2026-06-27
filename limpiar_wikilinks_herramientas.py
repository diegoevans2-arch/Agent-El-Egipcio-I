"""
limpiar_wikilinks_herramientas.py
Script de limpieza retroactiva: convierte wikilinks de herramientas
([[DBeaver]], [[Excel]], etc.) en texto plano, sin tocar wikilinks de
fuentes (Banner9, Athena, etc.) ni de personas.

Modo de uso (desde la carpeta del agente):
    python limpiar_wikilinks_herramientas.py            # dry-run, no modifica nada
    python limpiar_wikilinks_herramientas.py --ejecutar # aplica cambios reales

Hace backup automático en bitacoras/_backup_pre_limpieza/<fecha-hora>/
antes de tocar cualquier archivo.
"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

from utils import cargar_config, ruta_bitacoras, ruta_snippets
from bitacora import _MAPEO_HERRAMIENTAS, _MAPEO_FUENTES


def _construir_set_herramientas() -> set:
    """
    Devuelve el conjunto de NOMBRES (variantes) de herramientas que el script
    intentará desenlazar.

    Reglas:
    - Incluye los valores canónicos de _MAPEO_HERRAMIENTAS (DBeaver, Power BI, ...).
    - Incluye también las CLAVES del mapeo (microsoft teams, vscode, ...) para
      capturar todas las variantes que el agente podría haber escrito como
      wikilink en bitácoras pasadas.
    - EXCLUYE cualquier nombre cuyo valor canónico también aparezca en
      _MAPEO_FUENTES. Caso típico: "Athena" / "amazon athena" — están en
      ambos mapeos (Athena es herramienta de consulta sobre datos), pero
      las preservamos como fuente para mantener su nodo en el grafo.
    """
    fuentes_canonicas = set(_MAPEO_FUENTES.values())
    fuentes_claves = set(_MAPEO_FUENTES.keys())

    nombres = set()

    # Valores canónicos de herramientas
    for canonico in _MAPEO_HERRAMIENTAS.values():
        if canonico in fuentes_canonicas:
            continue  # solapamiento — preservar como fuente
        nombres.add(canonico)

    # Claves de herramientas: solo agregar si su valor canónico NO es fuente
    # y la clave en sí no es clave de fuente
    for clave, canonico in _MAPEO_HERRAMIENTAS.items():
        if canonico in fuentes_canonicas:
            continue  # mapea a una fuente — no tocar
        if clave in fuentes_claves:
            continue  # la clave también es alias de una fuente
        nombres.add(clave)

    return nombres


def _patron_wikilink_herramienta(nombre_herramienta: str) -> re.Pattern:
    """
    Construye un regex que matchea [[Nombre]] o [[Nombre|alias]] de manera
    case-insensitive. Captura el alias si existe.
    """
    # \[\[ Nombre (\| alias)? \]\]
    return re.compile(
        r"\[\[(" + re.escape(nombre_herramienta) + r")(\|([^\]]+))?\]\]",
        flags=re.IGNORECASE,
    )


def _limpiar_contenido(contenido: str, herramientas: set) -> tuple:
    """
    Procesa el contenido de un archivo .md y convierte cada wikilink de
    herramienta en texto plano (preservando el alias si existe).

    Retorna (contenido_nuevo, n_reemplazos).
    """
    nuevo = contenido
    total_reemplazos = 0

    # Ordenar por longitud descendente para evitar matches parciales
    # (ej: "Power BI" antes que "Power")
    orden = sorted(herramientas, key=len, reverse=True)

    for nombre in orden:
        patron = _patron_wikilink_herramienta(nombre)

        def reemplazar(m):
            # Si hay alias, preservarlo como texto
            alias = m.group(3)
            if alias:
                return alias
            # Sin alias, reemplazar por el nombre del wikilink (preserva caso original)
            return m.group(1)

        nuevo, n = patron.subn(reemplazar, nuevo)
        total_reemplazos += n

    return nuevo, total_reemplazos


def _hacer_backup(archivo: Path, dir_backup: Path):
    """Copia el archivo al directorio de backup preservando estructura relativa."""
    dir_backup.mkdir(parents=True, exist_ok=True)
    destino = dir_backup / archivo.name
    shutil.copy2(archivo, destino)


def main():
    dry_run = "--ejecutar" not in sys.argv

    config = cargar_config()
    ruta_base = ruta_bitacoras()

    if not ruta_base.exists():
        print(f"[ERROR] Carpeta de bitácoras no existe: {ruta_base}")
        return 1

    herramientas = _construir_set_herramientas()
    print(f"[Limpieza] Herramientas a desenlazar ({len(herramientas)}): "
          f"{', '.join(sorted(herramientas))}")
    print()

    if dry_run:
        print("⚠ MODO DRY-RUN — no se modificará ningún archivo.")
        print("   Para aplicar los cambios, ejecuta con --ejecutar")
        print()

    # Carpeta de backup (solo se crea si vamos a ejecutar)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dir_backup = ruta_base / "_backup_pre_limpieza" / timestamp

    # Recolectar archivos a procesar
    archivos = []
    archivos.extend(sorted(ruta_base.glob("bitacora_*.md")))
    snippets_dir = ruta_snippets()
    if snippets_dir.exists():
        archivos.extend(sorted(snippets_dir.glob("*.md")))

    # Estadísticas
    n_archivos_modificados = 0
    n_archivos_intactos = 0
    n_reemplazos_totales = 0
    detalle = []

    for archivo in archivos:
        try:
            original = archivo.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[Limpieza] Error leyendo {archivo.name}: {e}")
            continue

        nuevo, n = _limpiar_contenido(original, herramientas)

        if n == 0:
            n_archivos_intactos += 1
            continue

        n_archivos_modificados += 1
        n_reemplazos_totales += n
        detalle.append((archivo.relative_to(ruta_base), n))

        if not dry_run:
            try:
                _hacer_backup(archivo, dir_backup)
                archivo.write_text(nuevo, encoding="utf-8")
            except Exception as e:
                print(f"[Limpieza] Error escribiendo {archivo.name}: {e}")
                continue

    # Resumen
    print(f"{'=' * 60}")
    print(f"RESUMEN {'(DRY-RUN — sin cambios reales)' if dry_run else ''}")
    print(f"{'=' * 60}")
    print(f"Archivos revisados:    {len(archivos)}")
    print(f"Archivos modificados:  {n_archivos_modificados}")
    print(f"Archivos intactos:     {n_archivos_intactos}")
    print(f"Wikilinks limpiados:   {n_reemplazos_totales}")

    if detalle:
        print()
        print("Detalle por archivo (top 30):")
        for ruta_rel, n in sorted(detalle, key=lambda x: -x[1])[:30]:
            print(f"  {n:>4} reemplazos — {ruta_rel}")

    if not dry_run and n_archivos_modificados > 0:
        print()
        print(f"📁 Backup en: {dir_backup}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
