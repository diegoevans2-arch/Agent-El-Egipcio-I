"""
Detección híbrida de ventanas en monitor.py.

Cubre la función es_ventana_relevante() que decide si una ventana se
registra, y es_reunion() que detecta reuniones. Son funciones puras
(solo dependen del config pasado), así que se testean directo sin mocks
de win32.

Flujo de es_ventana_relevante:
  1. Proceso en lista_negra → False
  2. Browser/UWP host → filtrar por keywords del título
  3. App escritorio → match exacto contra lista_blanca
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# monitor.py importa win32gui/win32process (pywin32), que solo existe en
# Windows. Para testear la lógica pura (es_ventana_relevante, es_reunion)
# en cualquier OS, mockeamos esos módulos ANTES de importar monitor.
for _mod in ["win32gui", "win32process", "psutil"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from tests.conftest import config_minima
import monitor


class TestEsVentanaRelevante(unittest.TestCase):

    def setUp(self):
        self.config = config_minima("/tmp/fake")

    # --- Lista negra ---

    def test_proceso_lista_negra_se_ignora(self):
        # spotify.exe está en lista_negra
        self.assertFalse(
            monitor.es_ventana_relevante("Spotify", "spotify.exe", self.config)
        )

    def test_lista_negra_case_insensitive(self):
        self.assertFalse(
            monitor.es_ventana_relevante("Spotify", "SPOTIFY.EXE", self.config)
        )

    # --- App de escritorio (lista blanca) ---

    def test_app_escritorio_en_lista_blanca(self):
        # dbeaver.exe está en lista_blanca
        self.assertTrue(
            monitor.es_ventana_relevante("DBeaver - query", "dbeaver.exe", self.config)
        )

    def test_app_escritorio_no_en_lista_blanca(self):
        self.assertFalse(
            monitor.es_ventana_relevante("Bloc de notas", "notepad_xyz.exe", self.config)
        )

    def test_lista_blanca_case_insensitive(self):
        self.assertTrue(
            monitor.es_ventana_relevante("Excel", "EXCEL.EXE", self.config)
        )

    # --- Browser / UWP (filtrado por título) ---

    def test_browser_con_keyword_laboral(self):
        # chrome es host por título; "athena" es keyword laboral
        self.assertTrue(
            monitor.es_ventana_relevante(
                "AWS Athena Query Editor", "chrome.exe", self.config
            )
        )

    def test_browser_con_keyword_bloqueada(self):
        # "youtube" está en keywords_bloqueadas
        self.assertFalse(
            monitor.es_ventana_relevante(
                "YouTube - video", "chrome.exe", self.config
            )
        )

    def test_browser_sin_keyword_laboral(self):
        # Browser sin contenido laboral identificable → False
        self.assertFalse(
            monitor.es_ventana_relevante(
                "Página personal random", "chrome.exe", self.config
            )
        )

    def test_browser_bloqueada_tiene_prioridad(self):
        """
        Si el título tiene tanto keyword bloqueada como laboral, la bloqueada
        gana (se evalúa primero).
        """
        # "youtube" (bloqueada) + "jupyter" (laboral) en el mismo título
        self.assertFalse(
            monitor.es_ventana_relevante(
                "youtube tutorial de jupyter", "chrome.exe", self.config
            )
        )

    # --- Casos límite ---

    def test_titulo_none(self):
        # No debe reventar con título None
        resultado = monitor.es_ventana_relevante(None, "dbeaver.exe", self.config)
        self.assertTrue(resultado)  # dbeaver está en lista blanca

    def test_proceso_none(self):
        resultado = monitor.es_ventana_relevante("algo", None, self.config)
        self.assertIsInstance(resultado, bool)


class TestEsReunion(unittest.TestCase):

    def setUp(self):
        self.config = config_minima("/tmp/fake")

    def test_detecta_teams(self):
        self.assertTrue(
            monitor.es_reunion("Microsoft Teams Meeting", self.config)
        )

    def test_detecta_zoom(self):
        self.assertTrue(monitor.es_reunion("Zoom Meeting", self.config))

    def test_detecta_meet(self):
        self.assertTrue(monitor.es_reunion("Google Meet - reunión", self.config))

    def test_no_reunion(self):
        self.assertFalse(monitor.es_reunion("DBeaver - query SQL", self.config))

    def test_case_insensitive(self):
        self.assertTrue(monitor.es_reunion("MICROSOFT TEAMS", self.config))

    def test_titulo_none(self):
        self.assertFalse(monitor.es_reunion(None, self.config))


if __name__ == "__main__":
    unittest.main(verbosity=2)
