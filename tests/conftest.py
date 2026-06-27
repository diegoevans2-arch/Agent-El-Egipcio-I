"""
Helpers compartidos para la suite de QA.

Provee:
  - vault_temporal(): context manager que crea un vault temporal con
    config.json mínimo y lo limpia al salir.
  - config_minima(): dict de config válido para tests.
  - mock_cliente_ia(): MagicMock de ClienteIA con métodos estándar.

Diseño: los tests NO deben tocar el config.json real ni el vault real del
usuario. Todo se hace sobre directorios temporales con configs mockeadas.
"""

import os
import sys
import json
import shutil
import tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import MagicMock

# Asegurar que el directorio raíz del proyecto esté en el path
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


def config_minima(ruta_base: str) -> dict:
    """
    Retorna un dict de configuración mínimo pero válido para tests.
    ruta_base apunta al vault temporal.
    """
    return {
        "ia_proveedor": "claude",
        "ia_api_keys": {"claude": "test-key", "openai": "", "gemini": ""},
        "ia_modelos": {"claude": "claude-sonnet-4-6"},
        "nombre_usuario": "TestUser",
        "ruta_base": ruta_base,
        "ruta_obsidian_1": "obsidian",
        "ruta_obsidian_2": "",
        "dias_contexto_chat": 7,
        "system_prompt": "",
        "prompt_clasificacion": "",
        "prompt_imagen_actividad": "",
        "prompt_imagen_reunion": "",
        "monitor_captura": 1,
        "tema_visual": "mocha",
        "lista_blanca_procesos": ["dbeaver.exe", "excel.exe", "code.exe"],
        "lista_negra_procesos": ["spotify.exe", "whatsapp.exe"],
        "palabras_clave_laborales_browser": ["athena", "power bi", "jupyter"],
        "keywords_bloqueadas_browser": ["youtube", "netflix"],
        "palabras_clave_reunion": ["teams", "zoom", "meet"],
        "dominios_laborales": ["uss.cl", "aws.amazon.com"],
        "personas_conocidas": ["Pablo Rubilar", "Diego Perez"],
        "proyectos": [],
        "captura": {
            "estabilidad_segundos": 5,
            "intervalo_reunion_segundos": 120,
        },
        "alertas": {"inactividad_dias": 3},
        "finops": {"precios_override": {}},
    }


@contextmanager
def vault_temporal(nombre_vault: str = "Naos"):
    """
    Crea un vault temporal con un config.json mínimo y entrega la ruta.
    Limpia todo al salir.

    Yields:
        (ruta_vault: Path, config: dict)
    """
    tmpdir = tempfile.mkdtemp()
    try:
        ruta_vault = Path(tmpdir) / nombre_vault
        ruta_vault.mkdir(parents=True, exist_ok=True)
        config = config_minima(str(ruta_vault))
        yield ruta_vault, config
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def mock_cliente_ia(
    respuesta_clasificar: str = "ninguno",
    respuesta_chat: str = "respuesta de prueba",
    respuesta_imagen: str = None,
) -> MagicMock:
    """
    Crea un MagicMock de ClienteIA con los métodos estándar mockeados.

    respuesta_imagen, si es None, devuelve un JSON de actividad válido.
    """
    if respuesta_imagen is None:
        respuesta_imagen = json.dumps({
            "actividad": "tarea de prueba",
            "categoria": "SQL",
            "herramienta": "DBeaver",
            "urls": [],
        })

    cliente = MagicMock()
    cliente.clasificar.return_value = respuesta_clasificar
    cliente.chat.return_value = respuesta_chat
    cliente.analizar_imagen.return_value = respuesta_imagen
    cliente.proveedor = "claude"
    cliente.modelo = "claude-sonnet-4-6"
    cliente.modelo_rapido = "claude-haiku-4-5"
    return cliente


def escribir_config(ruta_vault: Path, config: dict, raiz_proyecto: Path):
    """
    Escribe un config.json en la raíz del proyecto (donde utils.cargar_config
    lo busca). Retorna la ruta del archivo escrito para poder restaurarlo.

    ADVERTENCIA: esto modifica el config.json real del proyecto. Solo usar
    en tests que hagan backup/restore. Preferir mockear cargar_config.
    """
    ruta_config = raiz_proyecto / "config.json"
    ruta_config.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return ruta_config
