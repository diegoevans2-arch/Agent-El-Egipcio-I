# 🧪 Suite de QA — El Egypcio

Suite de tests pre-productiva. Corre esto **antes de cada arranque en producción**
para verificar que ningún cambio rompió la funcionalidad existente.

## Uso

Desde la raíz del proyecto (donde está `agente.py`):

```bash
# Correr todo el QA
python tests/run_qa.py

# Con detalle de cada test (verbose)
python tests/run_qa.py -v

# Solo un módulo
python tests/run_qa.py --modulo gantt
python tests/run_qa.py --modulo finops

# Sin colores (para logs/CI)
python tests/run_qa.py --no-color
```

## Exit code

- `0` → todos los tests pasaron → **APTO PARA PRODUCCIÓN**
- `1` → hubo fallos o errores → **NO DESPLEGAR**

Esto permite usarlo en un pipeline o script de arranque:

```bash
python tests/run_qa.py --no-color && python agente.py
```

Si el QA falla, el agente no arranca.

## Qué cubre cada módulo

| Módulo | Cubre |
|---|---|
| `test_config_integrity` | Que `config_template.json` tenga todas las claves que el código consume |
| `test_utils_rutas` | Que cada helper de ruta del vault apunte a la carpeta correcta |
| `test_temas` | Que las 5 paletas existan con todas las claves de color consistentes |
| `test_monitor` | Lógica de detección híbrida (lista blanca/negra, keywords browser, reunión) |
| `test_cliente_ia` | Construcción multi-proveedor, clamp de temperatura, cliente global |
| `test_captura` | Prompts de imagen configurables, filtro de URLs, parsing de JSON |
| `test_finops` | Cálculo de costos, override de precios, agregación de tokens |
| `test_gantt` | Clasificación, temperatura, prompt configurable, persistencia de proyectos |
| `test_proyectos` | Creación de MOCs, slug, agrupación de rangos, detección de personas |
| `test_chat` | Keywords de tasks y manuales, normalización, detección de proyectos |

## Diseño

- **Aislamiento total**: ningún test toca el `config.json` real ni el vault real.
  Todo se hace sobre directorios temporales y configs mockeadas (ver `conftest.py`).
- **Sin dependencias de red ni API**: todas las llamadas al LLM se mockean.
  Los tests no gastan tokens ni requieren API keys.
- **Multi-OS**: aunque el agente es Windows-only (usa pywin32), los tests
  mockean los módulos de Windows para poder correr en cualquier sistema.
- **Sin efectos secundarios**: cada test limpia lo que crea (carpetas temporales).

## Agregar tests

Para agregar un módulo nuevo:

1. Crea `tests/test_<modulo>.py` siguiendo el patrón de los existentes.
2. Agrégalo a la lista `_MODULOS_TEST` en `run_qa.py`.
3. Usa los helpers de `conftest.py` (`vault_temporal`, `config_minima`,
   `mock_cliente_ia`) para no duplicar setup.

## Helpers compartidos (`conftest.py`)

- `vault_temporal()` — context manager que crea un vault temporal con
  `config.json` mínimo y lo limpia al salir.
- `config_minima(ruta_base)` — dict de config válido para tests.
- `mock_cliente_ia(...)` — MagicMock de ClienteIA con métodos estándar.
