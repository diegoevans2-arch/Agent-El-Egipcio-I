"""
finops.py
Módulo de monitoreo de consumo de API: registra tokens y costo de cada
llamada al LLM, agrupado por día. Provee funciones de consulta usadas por
la UI (popup de configuraciones → módulo FinOps).

Diseño:
- Persistencia AGREGADA POR DÍA en bitacoras/finops_data.json.
- Para cada día, totales por tipo de operación:
  captura_actividad, captura_reunion, clasificacion_proyecto,
  chat_usuario, resumen_dia, resumen_semana, validacion_key.
- Precios HARDCODED por modelo (en USD por millón de tokens).
- Override opcional desde config.json → sección "finops.precios".
- La fecha de actualización de los precios queda registrada en la UI.

Para agregar un modelo nuevo: añádelo a _PRECIOS_DEFAULT_USD.
Si los precios cambiaron, edita _PRECIOS_DEFAULT_USD o usa el override
en config.json bajo "finops.precios_override".
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from utils import cargar_config


# ===========================================================================
# Precios (USD por millón de tokens)
# ===========================================================================
# Fuente: precios públicos de cada proveedor al momento de la última
# actualización. Si los precios cambiaron, ajusta esta tabla o usa el
# override desde config.json.
#
# Formato: { "nombre_modelo": (precio_input, precio_output) }
# Los precios son por 1 MILLÓN de tokens.
# ---------------------------------------------------------------------------

PRECIOS_ACTUALIZADOS_FECHA = "2026-05-15"

_PRECIOS_DEFAULT_USD = {
    # Claude (Anthropic)
    "claude-opus-4-7":             (15.00, 75.00),
    "claude-opus-4-6":             (15.00, 75.00),
    "claude-sonnet-4-6":           (3.00,  15.00),
    "claude-haiku-4-5-20251001":   (0.80,  4.00),
    "claude-haiku-4-5":            (0.80,  4.00),

    # OpenAI
    "gpt-4o":                      (2.50,  10.00),
    "gpt-4o-mini":                 (0.15,  0.60),
    "gpt-4-turbo":                 (10.00, 30.00),
    "gpt-4":                       (30.00, 60.00),

    # Gemini (Google)
    "gemini-3.1-pro-preview":      (1.25,  10.00),
    "gemini-3-flash-preview":      (0.075, 0.30),
    "gemini-2.5-flash":            (0.075, 0.30),
}


def _obtener_precio(modelo: str) -> tuple:
    """
    Retorna (precio_input, precio_output) por 1M tokens para un modelo dado.
    Reglas:
    1. Override en config.json → finops.precios_override → wins.
    2. _PRECIOS_DEFAULT_USD → fallback.
    3. (0, 0) si el modelo es desconocido (logueado en consola).
    """
    try:
        cfg = cargar_config()
    except Exception:
        cfg = {}

    override = (cfg.get("finops") or {}).get("precios_override") or {}
    if modelo in override:
        entrada = override[modelo]
        if isinstance(entrada, (list, tuple)) and len(entrada) >= 2:
            return (float(entrada[0]), float(entrada[1]))

    if modelo in _PRECIOS_DEFAULT_USD:
        return _PRECIOS_DEFAULT_USD[modelo]

    print(f"[FinOps] ⚠ Modelo '{modelo}' sin precio configurado — costo se computa como 0.")
    return (0.0, 0.0)


def calcular_costo(modelo: str, tokens_input: int, tokens_output: int) -> float:
    """
    Calcula el costo en USD para una llamada dada.
    Retorna 0.0 si el modelo es desconocido.
    """
    precio_in, precio_out = _obtener_precio(modelo)
    costo_in = (tokens_input / 1_000_000) * precio_in
    costo_out = (tokens_output / 1_000_000) * precio_out
    return costo_in + costo_out


# ===========================================================================
# Tipos de operación trackeados
# ===========================================================================

TIPOS_OPERACION = (
    "captura_actividad",       # captura.py → analizar_imagen (es_reunion=False)
    "captura_reunion",         # captura.py → analizar_imagen (es_reunion=True)
    "clasificacion_proyecto",  # gantt.py → clasificar
    "chat_usuario",            # chat.py → responder
    "resumen_dia",             # chat.py → generar_resumen_dia
    "resumen_semana",          # chat.py → generar_resumen_semana
    "validacion_key",          # cliente_ia.validar_key
)

# Tipos visibles en el desglose del UI (no incluye validacion_key porque
# es uno solo al iniciar sesión y no aporta análisis útil).
TIPOS_OPERACION_UI = (
    "captura_actividad",
    "captura_reunion",
    "clasificacion_proyecto",
    "chat_usuario",
    "resumen_dia",
    "resumen_semana",
)

# Labels visibles para la UI
ETIQUETAS_OPERACION = {
    "captura_actividad":      "📸 Captura actividad",
    "captura_reunion":        "🎥 Captura reunión",
    "clasificacion_proyecto": "🎯 Clasif. proyecto",
    "chat_usuario":           "💬 Chat usuario",
    "resumen_dia":            "📋 Resumen día",
    "resumen_semana":         "📋 Resumen semana",
    "validacion_key":         "🔑 Validación key",
}


# ===========================================================================
# Persistencia
# ===========================================================================
# Archivo: bitacoras/finops_data.json
# Estructura:
# {
#   "version": 1,
#   "registros_por_dia": {
#     "2026-05-15": {
#       "captura_actividad": {
#         "llamadas": 89,
#         "tokens_input": 137000,
#         "tokens_output": 16800,
#         "costo_usd": 0.663,
#         "modelos": {"claude-sonnet-4-6": 89}
#       },
#       ...
#     }
#   }
# }
# ---------------------------------------------------------------------------

_VERSION = 1


def _ruta_data() -> Path:
    """Retorna ruta de bitacoras/finops_data.json (crea la carpeta si falta)."""
    cfg = cargar_config()
    ruta = Path(cfg["ruta_base"]) / "bitacoras"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta / "finops_data.json"


def _cargar_data() -> dict:
    """Carga el archivo de datos. Si no existe o está corrupto, retorna inicial."""
    ruta = _ruta_data()
    if not ruta.exists():
        return {"version": _VERSION, "registros_por_dia": {}}
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
        # Migración futura: si data["version"] < _VERSION, migrar aquí.
        if "registros_por_dia" not in data:
            data["registros_por_dia"] = {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[FinOps] ⚠ Error leyendo {ruta.name}: {e}. Reiniciando archivo.")
        return {"version": _VERSION, "registros_por_dia": {}}


def _guardar_data(data: dict):
    """Persiste el archivo de datos."""
    try:
        with open(_ruta_data(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[FinOps] ⚠ Error escribiendo finops_data.json: {e}")


# ===========================================================================
# Registro (lo que llama el interceptor de cliente_ia)
# ===========================================================================

def registrar_uso(tipo: str, modelo: str,
                  tokens_input: int = 0, tokens_output: int = 0) -> None:
    """
    Registra una llamada al LLM en los agregados del día actual.

    Args:
        tipo: uno de TIPOS_OPERACION (los desconocidos se logean pero igual
              se acumulan bajo el tipo provisto, para no perder datos).
        modelo: nombre del modelo usado (ej. "claude-sonnet-4-6").
        tokens_input: tokens de entrada según API.
        tokens_output: tokens de salida según API.

    Nunca lanza excepción: si algo falla, lo logea y sigue. FinOps es
    observabilidad — no debe romper el flujo principal del agente.
    """
    if tipo not in TIPOS_OPERACION:
        print(f"[FinOps] ⚠ Tipo desconocido '{tipo}' — se registra de todos modos.")

    try:
        tokens_input = max(0, int(tokens_input or 0))
        tokens_output = max(0, int(tokens_output or 0))
        costo = calcular_costo(modelo, tokens_input, tokens_output)

        data = _cargar_data()
        hoy = datetime.now().strftime("%Y-%m-%d")
        registros = data["registros_por_dia"]
        if hoy not in registros:
            registros[hoy] = {}
        if tipo not in registros[hoy]:
            registros[hoy][tipo] = {
                "llamadas": 0,
                "tokens_input": 0,
                "tokens_output": 0,
                "costo_usd": 0.0,
                "modelos": {},
            }
        reg = registros[hoy][tipo]
        reg["llamadas"] += 1
        reg["tokens_input"] += tokens_input
        reg["tokens_output"] += tokens_output
        reg["costo_usd"] = round(reg["costo_usd"] + costo, 6)
        reg["modelos"][modelo] = reg["modelos"].get(modelo, 0) + 1

        _guardar_data(data)
    except Exception as e:
        # FinOps nunca debe romper la operación principal
        print(f"[FinOps] ⚠ Error registrando uso: {e}")


# ===========================================================================
# Consultas (las usa la UI)
# ===========================================================================

def _suma_dia(reg_dia: dict, campo: str) -> float:
    """Suma un campo a través de todos los tipos en un día."""
    if not reg_dia:
        return 0.0
    return sum(t.get(campo, 0) for t in reg_dia.values())


def resumen_dia(fecha: str = None) -> dict:
    """
    Retorna un dict con totales del día especificado.
    Si fecha es None → hoy.
    """
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")

    data = _cargar_data()
    reg_dia = data["registros_por_dia"].get(fecha, {})

    total_llamadas = int(_suma_dia(reg_dia, "llamadas"))
    total_tokens = int(_suma_dia(reg_dia, "tokens_input") + _suma_dia(reg_dia, "tokens_output"))
    total_costo = round(_suma_dia(reg_dia, "costo_usd"), 4)

    # Desglose por tipo
    desglose = []
    for tipo in TIPOS_OPERACION_UI:
        reg = reg_dia.get(tipo, {})
        if not reg:
            continue
        desglose.append({
            "tipo": tipo,
            "etiqueta": ETIQUETAS_OPERACION.get(tipo, tipo),
            "llamadas": int(reg.get("llamadas", 0)),
            "costo_usd": round(reg.get("costo_usd", 0.0), 4),
            "porcentaje": round((reg.get("costo_usd", 0.0) / total_costo * 100), 1)
                          if total_costo > 0 else 0.0,
        })
    # Ordenar por costo descendente
    desglose.sort(key=lambda x: x["costo_usd"], reverse=True)

    return {
        "fecha": fecha,
        "total_llamadas": total_llamadas,
        "total_tokens": total_tokens,
        "total_costo": total_costo,
        "desglose_por_tipo": desglose,
    }


def resumen_mes(mes: str = None) -> dict:
    """
    Retorna totales del mes especificado (formato 'YYYY-MM').
    Si mes es None → mes actual.
    """
    if mes is None:
        mes = datetime.now().strftime("%Y-%m")

    data = _cargar_data()
    registros = data["registros_por_dia"]

    total_llamadas = 0
    total_tokens = 0
    total_costo = 0.0

    for fecha, reg_dia in registros.items():
        if not fecha.startswith(mes):
            continue
        total_llamadas += int(_suma_dia(reg_dia, "llamadas"))
        total_tokens += int(_suma_dia(reg_dia, "tokens_input") + _suma_dia(reg_dia, "tokens_output"))
        total_costo += _suma_dia(reg_dia, "costo_usd")

    return {
        "mes": mes,
        "total_llamadas": total_llamadas,
        "total_tokens": total_tokens,
        "total_costo": round(total_costo, 4),
    }


def historico_ultimos_dias(n_dias: int = 5) -> list:
    """
    Retorna una lista con los últimos N días (incluyendo hoy), cada uno con
    su costo. Los días sin actividad aparecen con costo 0 para no romper
    el gráfico.

    Lista en orden cronológico ascendente (hoy al final).
    """
    data = _cargar_data()
    registros = data["registros_por_dia"]

    resultado = []
    hoy = datetime.now().date()
    for i in range(n_dias - 1, -1, -1):
        fecha_dt = hoy - timedelta(days=i)
        fecha_str = fecha_dt.strftime("%Y-%m-%d")
        reg_dia = registros.get(fecha_str, {})
        costo = round(_suma_dia(reg_dia, "costo_usd"), 4)
        llamadas = int(_suma_dia(reg_dia, "llamadas"))
        resultado.append({
            "fecha": fecha_str,
            "dia": fecha_dt.strftime("%a"),  # Lu, Ma, ...
            "costo_usd": costo,
            "llamadas": llamadas,
        })
    return resultado


# ===========================================================================
# Gestión del archivo
# ===========================================================================

def limpiar_historico() -> bool:
    """
    Borra TODO el histórico de uso. Acción destructiva.
    Retorna True si se limpió, False si hubo error.
    """
    try:
        data = {"version": _VERSION, "registros_por_dia": {}}
        _guardar_data(data)
        print("[FinOps] Histórico limpiado.")
        return True
    except Exception as e:
        print(f"[FinOps] ⚠ Error limpiando histórico: {e}")
        return False


def info_precios() -> dict:
    """
    Retorna info sobre los precios actualmente configurados, para mostrar
    en la UI ("Modelo actual: X, precio: $A/$B, última actualización: Y").
    """
    try:
        cfg = cargar_config()
    except Exception:
        cfg = {}
    proveedor = cfg.get("ia_proveedor", "claude")
    modelo = (cfg.get("ia_modelos") or {}).get(proveedor, "")

    precio_in, precio_out = _obtener_precio(modelo) if modelo else (0.0, 0.0)
    override_activo = modelo in ((cfg.get("finops") or {}).get("precios_override") or {})

    return {
        "proveedor": proveedor,
        "modelo": modelo,
        "precio_input_por_millon": precio_in,
        "precio_output_por_millon": precio_out,
        "override_activo": override_activo,
        "actualizado_al": PRECIOS_ACTUALIZADOS_FECHA,
    }
