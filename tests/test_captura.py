"""
Captura y análisis de imágenes en captura.py.

Cubre:
1. validar_prompt_imagen: placeholder {titulo_ventana} obligatorio
2. cargar_prompt_imagen: fallback a default (reunión y actividad independientes)
3. _filtrar_urls_laborales: filtrado por dominio, dedup, robustez
4. analizar_screenshot: usa template custom, parsea JSON, fallback ante errores
"""

import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import captura


class TestValidarPromptImagen(unittest.TestCase):

    def test_defaults_validos(self):
        for default in [captura.PROMPT_IMAGEN_ACTIVIDAD_DEFAULT,
                        captura.PROMPT_IMAGEN_REUNION_DEFAULT]:
            valido, faltantes = captura.validar_prompt_imagen(default)
            self.assertTrue(valido)
            self.assertEqual(faltantes, [])

    def test_falta_placeholder(self):
        valido, faltantes = captura.validar_prompt_imagen("sin placeholder")
        self.assertFalse(valido)
        self.assertEqual(faltantes, ["titulo_ventana"])

    def test_vacio_y_none(self):
        for val in ["", None]:
            valido, faltantes = captura.validar_prompt_imagen(val)
            self.assertFalse(valido)


class TestCargarPromptImagen(unittest.TestCase):

    def test_fallback_actividad(self):
        with patch.object(captura, "cargar_config", return_value={}):
            p = captura.cargar_prompt_imagen(es_reunion=False)
        self.assertEqual(p, captura.PROMPT_IMAGEN_ACTIVIDAD_DEFAULT)

    def test_fallback_reunion(self):
        with patch.object(captura, "cargar_config", return_value={}):
            p = captura.cargar_prompt_imagen(es_reunion=True)
        self.assertEqual(p, captura.PROMPT_IMAGEN_REUNION_DEFAULT)

    def test_custom_valido(self):
        custom = "Custom {titulo_ventana}"
        with patch.object(captura, "cargar_config",
                          return_value={"prompt_imagen_actividad": custom}):
            p = captura.cargar_prompt_imagen(es_reunion=False)
        self.assertEqual(p, custom)

    def test_custom_invalido_cae_a_default(self):
        with patch.object(captura, "cargar_config",
                          return_value={"prompt_imagen_actividad": "sin ph"}):
            p = captura.cargar_prompt_imagen(es_reunion=False)
        self.assertEqual(p, captura.PROMPT_IMAGEN_ACTIVIDAD_DEFAULT)

    def test_independencia_actividad_reunion(self):
        config = {"prompt_imagen_actividad": "Act {titulo_ventana}"}
        with patch.object(captura, "cargar_config", return_value=config):
            p_act = captura.cargar_prompt_imagen(es_reunion=False)
            p_reu = captura.cargar_prompt_imagen(es_reunion=True)
        self.assertEqual(p_act, "Act {titulo_ventana}")
        self.assertEqual(p_reu, captura.PROMPT_IMAGEN_REUNION_DEFAULT)


class TestFiltrarUrls(unittest.TestCase):

    def test_filtra_por_dominio(self):
        urls = ["https://uss.cl/page", "https://random.com/x"]
        dominios = ["uss.cl"]
        resultado = captura._filtrar_urls_laborales(urls, dominios)
        self.assertEqual(resultado, ["https://uss.cl/page"])

    def test_sin_dominios_retorna_vacio(self):
        urls = ["https://uss.cl/page"]
        self.assertEqual(captura._filtrar_urls_laborales(urls, []), [])

    def test_sin_urls_retorna_vacio(self):
        self.assertEqual(captura._filtrar_urls_laborales([], ["uss.cl"]), [])

    def test_deduplica(self):
        urls = ["https://uss.cl/a", "https://uss.cl/a"]
        resultado = captura._filtrar_urls_laborales(urls, ["uss.cl"])
        self.assertEqual(len(resultado), 1)

    def test_case_insensitive(self):
        urls = ["https://USS.CL/page"]
        resultado = captura._filtrar_urls_laborales(urls, ["uss.cl"])
        self.assertEqual(len(resultado), 1)

    def test_ignora_no_strings(self):
        urls = ["https://uss.cl/ok", None, 123, ""]
        resultado = captura._filtrar_urls_laborales(urls, ["uss.cl"])
        self.assertEqual(resultado, ["https://uss.cl/ok"])


class TestAnalizarScreenshot(unittest.TestCase):

    def _mock_cliente(self, respuesta_json):
        cliente = MagicMock()
        cliente.analizar_imagen.return_value = respuesta_json
        return cliente

    def test_parsea_json_actividad(self):
        respuesta = json.dumps({
            "actividad": "query SQL", "categoria": "SQL",
            "herramienta": "DBeaver", "urls": []
        })
        cliente = self._mock_cliente(respuesta)
        with patch.object(captura, "get_cliente", return_value=cliente), \
             patch.object(captura, "cargar_config",
                          return_value={"dominios_laborales": []}):
            resultado = captura.analizar_screenshot("V", False, "fake_b64")
        self.assertEqual(resultado["categoria"], "SQL")
        self.assertEqual(resultado["herramienta"], "DBeaver")

    def test_json_invalido_devuelve_fallback(self):
        """Si el LLM devuelve algo que no es JSON, retorna fallback sin reventar."""
        cliente = self._mock_cliente("esto no es json {{{")
        with patch.object(captura, "get_cliente", return_value=cliente), \
             patch.object(captura, "cargar_config",
                          return_value={"dominios_laborales": []}):
            resultado = captura.analizar_screenshot("V", False, "fake_b64")
        # Debe tener estructura de fallback
        self.assertIn("actividad", resultado)
        self.assertIn("categoria", resultado)

    def test_limpia_markdown_en_respuesta(self):
        """El LLM a veces envuelve el JSON en ```json ... ```."""
        respuesta = "```json\n" + json.dumps({
            "actividad": "x", "categoria": "Python",
            "herramienta": "Jupyter", "urls": []
        }) + "\n```"
        cliente = self._mock_cliente(respuesta)
        with patch.object(captura, "get_cliente", return_value=cliente), \
             patch.object(captura, "cargar_config",
                          return_value={"dominios_laborales": []}):
            resultado = captura.analizar_screenshot("V", False, "fake_b64")
        self.assertEqual(resultado["categoria"], "Python")

    def test_usa_template_custom(self):
        custom = "CUSTOM {titulo_ventana}"
        respuesta = json.dumps({
            "actividad": "x", "categoria": "Otro",
            "herramienta": "y", "urls": []
        })
        cliente = self._mock_cliente(respuesta)
        with patch.object(captura, "cargar_prompt_imagen", return_value=custom), \
             patch.object(captura, "get_cliente", return_value=cliente), \
             patch.object(captura, "cargar_config",
                          return_value={"dominios_laborales": []}):
            captura.analizar_screenshot("MiVentana", False, "fake_b64")
        prompt = cliente.analizar_imagen.call_args.args[0]
        self.assertIn("CUSTOM MiVentana", prompt)

    def test_template_roto_cae_a_default(self):
        template_roto = "{titulo_ventana} {extra_no_dado}"
        respuesta = json.dumps({
            "actividad": "x", "categoria": "Otro",
            "herramienta": "y", "urls": []
        })
        cliente = self._mock_cliente(respuesta)
        with patch.object(captura, "cargar_prompt_imagen", return_value=template_roto), \
             patch.object(captura, "get_cliente", return_value=cliente), \
             patch.object(captura, "cargar_config",
                          return_value={"dominios_laborales": []}):
            resultado = captura.analizar_screenshot("V", False, "fake_b64")
        # No revienta y usa el default
        self.assertEqual(resultado["categoria"], "Otro")
        prompt = cliente.analizar_imagen.call_args.args[0]
        self.assertIn("área de datos/analytics", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
