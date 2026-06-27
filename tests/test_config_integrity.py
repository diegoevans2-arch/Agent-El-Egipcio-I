"""
Integridad de config_template.json.

Verifica que el template de configuración:
1. Es JSON válido
2. Contiene todas las claves que el código consume vía config.get(...)
3. Tiene las claves nuevas de las features recientes (prompts configurables)

La idea es atrapar el caso en que se agrega una feature que lee una clave
de config pero se olvida agregarla al template — lo que dejaría a usuarios
nuevos sin esa configuración.
"""

import sys
import json
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


class TestConfigTemplate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ruta = _RAIZ / "config_template.json"
        cls.existe = cls.ruta.exists()
        if cls.existe:
            cls.config = json.loads(cls.ruta.read_text(encoding="utf-8"))
        else:
            cls.config = {}

    def test_template_existe(self):
        self.assertTrue(self.existe,
                        f"config_template.json no existe en {self.ruta}")

    def test_es_json_valido(self):
        # Si llegó hasta acá sin excepción en setUpClass, ya es válido.
        self.assertIsInstance(self.config, dict)

    def test_claves_esenciales_presentes(self):
        """Claves que el código consume y deben existir en el template."""
        claves_esperadas = {
            "ia_proveedor", "ia_api_keys", "ia_modelos",
            "nombre_usuario", "ruta_base",
            "ruta_obsidian_1", "ruta_obsidian_2",
            "dias_contexto_chat",
            "system_prompt",
            "monitor_captura",
            "tema_visual",
            "lista_blanca_procesos", "lista_negra_procesos",
            "palabras_clave_laborales_browser", "keywords_bloqueadas_browser",
            "palabras_clave_reunion",
            "dominios_laborales",
            "personas_conocidas",
            "proyectos",
            "captura",
            "alertas",
        }
        faltantes = claves_esperadas - set(self.config.keys())
        self.assertEqual(faltantes, set(),
                         f"Faltan claves en config_template: {faltantes}")

    def test_claves_prompts_configurables(self):
        """Claves de las features de prompts configurables (recientes)."""
        claves_prompts = {
            "prompt_clasificacion",
            "prompt_imagen_actividad",
            "prompt_imagen_reunion",
        }
        faltantes = claves_prompts - set(self.config.keys())
        self.assertEqual(faltantes, set(),
                         f"Faltan claves de prompts: {faltantes}")

    def test_subclave_captura(self):
        """La sección captura debe tener las claves de tiempos."""
        captura = self.config.get("captura", {})
        self.assertIn("estabilidad_segundos", captura)
        self.assertIn("intervalo_reunion_segundos", captura)

    def test_subclave_alertas(self):
        alertas = self.config.get("alertas", {})
        self.assertIn("inactividad_dias", alertas)

    def test_ia_api_keys_es_dict(self):
        """ia_api_keys debe ser un dict con los 3 proveedores."""
        keys = self.config.get("ia_api_keys", {})
        self.assertIsInstance(keys, dict)
        for prov in ["claude", "openai", "gemini"]:
            self.assertIn(prov, keys, f"Falta proveedor '{prov}' en ia_api_keys")

    def test_proyectos_es_lista(self):
        self.assertIsInstance(self.config.get("proyectos"), list)

    def test_prompts_vacios_por_defecto(self):
        """
        Los prompts configurables deben venir vacíos en el template, para
        que se use el default del código. Un usuario nuevo no debería tener
        un prompt custom pre-cargado.
        """
        self.assertEqual(self.config.get("prompt_clasificacion", ""), "")
        self.assertEqual(self.config.get("prompt_imagen_actividad", ""), "")
        self.assertEqual(self.config.get("prompt_imagen_reunion", ""), "")
        self.assertEqual(self.config.get("system_prompt", ""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
