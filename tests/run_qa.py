#!/usr/bin/env python3
"""
run_qa.py — Runner único de la suite de QA del agente El Egypcio.

Ejecuta TODOS los módulos de test y produce un reporte consolidado,
módulo por módulo, con conteo de éxitos/fallos/errores y un veredicto
final apto para correr ANTES de un arranque productivo.

Uso:
    python tests/run_qa.py              # corre todo
    python tests/run_qa.py -v           # verbose (detalle de cada test)
    python tests/run_qa.py --modulo gantt   # solo un módulo

Exit code:
    0 → todos los tests pasaron (apto para producción)
    1 → hubo fallos o errores (NO desplegar)
"""

import sys
import time
import argparse
import unittest
from pathlib import Path

# Raíz del proyecto en el path
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# Módulos de test del paquete, en orden lógico (cimientos primero)
_MODULOS_TEST = [
    ("tests.test_config_integrity", "Integridad de config_template"),
    ("tests.test_utils_rutas",      "Rutas del vault (utils)"),
    ("tests.test_temas",            "Temas visuales (paletas)"),
    ("tests.test_monitor",          "Detección de ventanas (monitor)"),
    ("tests.test_cliente_ia",       "Cliente IA (multi-proveedor)"),
    ("tests.test_captura",          "Captura y análisis de imágenes"),
    ("tests.test_finops",           "FinOps (costos y tokens)"),
    ("tests.test_gantt",            "Gantt y clasificación de proyectos"),
    ("tests.test_proyectos",        "Proyectos (MOCs y migración)"),
    ("tests.test_chat",             "Chat (contexto y keywords)"),
]

# Colores ANSI (se desactivan si no es TTY)
class C:
    VERDE = "\033[92m"
    ROJO = "\033[91m"
    AMARILLO = "\033[93m"
    AZUL = "\033[94m"
    NEGRITA = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def desactivar(cls):
        cls.VERDE = cls.ROJO = cls.AMARILLO = cls.AZUL = cls.NEGRITA = cls.RESET = ""


def _correr_modulo(nombre_modulo: str, verbose: bool):
    """
    Corre un módulo de test y retorna:
        (run, fallos, errores, skipped, detalle_corto, detalle_completo)

    - detalle_corto: solo nombres de tests fallidos (para el reporte en pantalla)
    - detalle_completo: nombres + tracebacks (para el log de diagnóstico)

    Si el módulo no puede importarse, lo reporta como error de carga.
    """
    import io
    import contextlib

    loader = unittest.TestLoader()
    try:
        suite = loader.loadTestsFromName(nombre_modulo)
    except Exception as e:
        msg = f"ERROR DE CARGA: {e}"
        return (0, 0, 1, 0, msg, msg)

    if verbose:
        # En verbose mostramos todo (incluido el output del código bajo test)
        runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)
        resultado = runner.run(suite)
    else:
        # En modo normal silenciamos tanto el reporte de unittest como los
        # prints del código bajo test (que loguea fallbacks intencionales).
        buffer_resultado = io.StringIO()
        runner = unittest.TextTestRunner(stream=buffer_resultado, verbosity=0)
        with contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            resultado = runner.run(suite)

    detalle_corto = ""
    detalle_completo = ""
    if resultado.failures or resultado.errors:
        partes_corto = []
        partes_completo = []
        for test, tb in resultado.failures:
            partes_corto.append(f"  FALLO: {test}")
            partes_completo.append(f"  FALLO: {test}\n{tb}")
        for test, tb in resultado.errors:
            partes_corto.append(f"  ERROR: {test}")
            partes_completo.append(f"  ERROR: {test}\n{tb}")
        detalle_corto = "\n".join(partes_corto)
        detalle_completo = "\n".join(partes_completo)

    return (
        resultado.testsRun,
        len(resultado.failures),
        len(resultado.errors),
        len(getattr(resultado, "skipped", [])),
        detalle_corto,
        detalle_completo,
    )


def correr_qa_para_arranque():
    """
    Corre TODA la suite de QA en silencio y devuelve los resultados como
    datos, sin imprimir ni terminar el proceso.

    Pensada para llamarse desde agente.py como gate de arranque. A diferencia
    de main() (que es para línea de comandos), esta función no usa colores,
    no hace sys.exit, y captura cualquier excepción del propio runner para
    nunca dejar al agente sin poder arrancar.

    Returns:
        dict con:
          - "ok" (bool): True si todos los tests pasaron
          - "total" (int): total de tests corridos
          - "exitosos" (int)
          - "fallos" (int)
          - "errores" (int)
          - "modulos_con_problemas" (list[str]): descripciones legibles
          - "detalle" (str): texto con qué falló y los tracebacks, apto para
            escribir a un log de diagnóstico
          - "gate_concluyente" (bool): False si el runner mismo explotó
            (no si un test falló) — en ese caso conviene permitir bypass.
    """
    import io
    import contextlib

    total = exitosos = fallos = errores = 0
    modulos_con_problemas = []
    bloques_detalle = []
    gate_concluyente = True

    try:
        for nombre_modulo, descripcion in _MODULOS_TEST:
            try:
                run, n_fallos, n_errores, _skip, _corto, detalle = _correr_modulo(
                    nombre_modulo, verbose=False
                )
            except Exception as e:
                # Falló el runner para este módulo (no un test) — lo tratamos
                # como problema pero seguimos con los demás módulos.
                gate_concluyente = False
                run, n_fallos, n_errores, detalle = 0, 0, 1, f"EXCEPCIÓN DEL RUNNER: {e}"

            total += run
            fallos += n_fallos
            errores += n_errores

            if n_fallos or n_errores:
                modulos_con_problemas.append(descripcion)
                if detalle:
                    bloques_detalle.append(f"[{descripcion}]\n{detalle}")

        exitosos = total - fallos - errores

    except Exception as e:
        # Algo explotó en el bucle mismo — el gate no es concluyente.
        gate_concluyente = False
        bloques_detalle.append(f"EXCEPCIÓN GENERAL DEL GATE: {e}")
        errores += 1

    ok = (fallos == 0 and errores == 0)

    return {
        "ok": ok,
        "total": total,
        "exitosos": exitosos,
        "fallos": fallos,
        "errores": errores,
        "modulos_con_problemas": modulos_con_problemas,
        "detalle": "\n\n".join(bloques_detalle),
        "gate_concluyente": gate_concluyente,
    }


def main():
    parser = argparse.ArgumentParser(description="QA suite del agente El Egypcio")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Muestra el detalle de cada test")
    parser.add_argument("--modulo", type=str, default=None,
                        help="Corre solo un módulo (ej: gantt, finops)")
    parser.add_argument("--no-color", action="store_true",
                        help="Desactiva colores ANSI")
    args = parser.parse_args()

    if args.no_color or not sys.stdout.isatty():
        C.desactivar()

    # Filtrar módulos si se pidió uno específico
    modulos = _MODULOS_TEST
    if args.modulo:
        modulos = [
            (m, d) for m, d in _MODULOS_TEST
            if args.modulo.lower() in m.lower()
        ]
        if not modulos:
            print(f"{C.ROJO}No se encontró ningún módulo que coincida con "
                  f"'{args.modulo}'{C.RESET}")
            print(f"Módulos disponibles: "
                  f"{', '.join(m.split('.')[-1].replace('test_', '') for m, _ in _MODULOS_TEST)}")
            return 1

    print()
    print(f"{C.NEGRITA}{C.AZUL}{'=' * 70}{C.RESET}")
    print(f"{C.NEGRITA}{C.AZUL}  QA SUITE — El Egypcio · Verificación pre-productiva{C.RESET}")
    print(f"{C.NEGRITA}{C.AZUL}{'=' * 70}{C.RESET}")
    print()

    t0 = time.time()
    total_run = total_fallos = total_errores = total_skip = 0
    modulos_con_problemas = []
    detalles_problemas = []

    for nombre_modulo, descripcion in modulos:
        run, fallos, errores, skip, detalle, _completo = _correr_modulo(
            nombre_modulo, args.verbose
        )
        total_run += run
        total_fallos += fallos
        total_errores += errores
        total_skip += skip

        ok = (fallos == 0 and errores == 0)
        if ok:
            estado = f"{C.VERDE}✅ PASS{C.RESET}"
        else:
            estado = f"{C.ROJO}❌ FAIL{C.RESET}"
            modulos_con_problemas.append(descripcion)
            if detalle:
                detalles_problemas.append(f"\n[{descripcion}]\n{detalle}")

        # Línea de resumen del módulo
        contador = f"{run} tests"
        if skip:
            contador += f", {skip} skip"
        print(f"  {estado}  {descripcion:<42} {C.AMARILLO}{contador}{C.RESET}")

    elapsed = time.time() - t0

    # Detalles de problemas (si los hay)
    if detalles_problemas:
        print()
        print(f"{C.ROJO}{'-' * 70}{C.RESET}")
        print(f"{C.ROJO}{C.NEGRITA}DETALLE DE FALLOS Y ERRORES{C.RESET}")
        print(f"{C.ROJO}{'-' * 70}{C.RESET}")
        for d in detalles_problemas:
            print(d)

    # Veredicto final
    print()
    print(f"{C.NEGRITA}{'=' * 70}{C.RESET}")
    exito_total = total_run - total_fallos - total_errores
    print(f"{C.NEGRITA}  TOTAL: {total_run} tests en {elapsed:.2f}s{C.RESET}")
    print(f"    {C.VERDE}✅ Exitosos: {exito_total}{C.RESET}")
    if total_fallos:
        print(f"    {C.ROJO}❌ Fallos:   {total_fallos}{C.RESET}")
    if total_errores:
        print(f"    {C.ROJO}💥 Errores:  {total_errores}{C.RESET}")
    if total_skip:
        print(f"    {C.AMARILLO}⏭  Omitidos: {total_skip}{C.RESET}")
    print(f"{C.NEGRITA}{'=' * 70}{C.RESET}")

    todo_ok = (total_fallos == 0 and total_errores == 0)
    print()
    if todo_ok:
        print(f"{C.VERDE}{C.NEGRITA}  ✅ APTO PARA PRODUCCIÓN — todos los tests pasaron.{C.RESET}")
    else:
        print(f"{C.ROJO}{C.NEGRITA}  ❌ NO DESPLEGAR — revisa los problemas arriba.{C.RESET}")
        print(f"{C.ROJO}     Módulos con problemas: "
              f"{', '.join(modulos_con_problemas)}{C.RESET}")
    print()

    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
