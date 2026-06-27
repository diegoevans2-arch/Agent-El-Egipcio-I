"""
Gantt y clasificación de proyectos en gantt.py.

Cubre:
1. Helpers de campo (descripcion/objetivos/temperatura) con fallback legacy
2. validar_prompt_clasificacion y cargar_prompt_clasificacion
3. clasificar_actividad: prompt estructurado, temperatura, fallback de template
4. agregar/editar_proyecto: persistencia de la nueva estructura
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import gantt


class TestHelpersCampo(unittest.TestCase):

    def test_descripcion_campo_nuevo(self):
        p = {"descripcion": "nueva", "palabras_clave": "vieja"}
        self.assertEqual(gantt.obtener_descripcion(p), "nueva")

    def test_descripcion_fallback_legacy(self):
        self.assertEqual(gantt.obtener_descripcion({"palabras_clave": "vieja"}), "vieja")

    def test_descripcion_vacia(self):
        self.assertEqual(gantt.obtener_descripcion({}), "")

    def test_objetivos(self):
        self.assertEqual(gantt.obtener_objetivos({"objetivos": "obj"}), "obj")
        self.assertEqual(gantt.obtener_objetivos({}), "")

    def test_temperatura_default(self):
        self.assertEqual(gantt.obtener_temperatura({}), gantt.TEMPERATURA_DEFAULT)

    def test_temperatura_clamp(self):
        self.assertEqual(gantt.obtener_temperatura({"temperatura": 5.0}), 1.0)
        self.assertEqual(gantt.obtener_temperatura({"temperatura": -1.0}), 0.0)

    def test_temperatura_invalida(self):
        self.assertEqual(
            gantt.obtener_temperatura({"temperatura": "nan"}),
            gantt.TEMPERATURA_DEFAULT
        )


class TestPromptClasificacion(unittest.TestCase):

    def test_default_valido(self):
        valido, faltantes = gantt.validar_prompt_clasificacion(
            gantt.PROMPT_CLASIFICACION_DEFAULT
        )
        self.assertTrue(valido)
        self.assertEqual(faltantes, [])

    def test_falta_un_placeholder(self):
        prompt = ("{titulo_ventana} {descripcion_actividad} {lista_proyectos}")
        valido, faltantes = gantt.validar_prompt_clasificacion(prompt)
        self.assertFalse(valido)
        self.assertIn("lista_nombres", faltantes)

    def test_vacio_invalido(self):
        valido, _ = gantt.validar_prompt_clasificacion("")
        self.assertFalse(valido)

    def test_cargar_sin_config_usa_default(self):
        with patch.object(gantt, "cargar_config", return_value={}):
            self.assertEqual(
                gantt.cargar_prompt_clasificacion(),
                gantt.PROMPT_CLASIFICACION_DEFAULT
            )

    def test_cargar_custom_invalido_cae_a_default(self):
        with patch.object(gantt, "cargar_config",
                          return_value={"prompt_clasificacion": "solo {titulo_ventana}"}):
            self.assertEqual(
                gantt.cargar_prompt_clasificacion(),
                gantt.PROMPT_CLASIFICACION_DEFAULT
            )


class TestClasificarActividad(unittest.TestCase):

    def _proyectos(self):
        return [
            {"nombre": "Proyecto A", "descripcion": "Desc A",
             "objetivos": "Obj A", "temperatura": 0.1, "estado": "activo"},
            {"nombre": "Proyecto B", "descripcion": "Desc B",
             "objetivos": "Obj B", "temperatura": 0.3, "estado": "activo"},
        ]

    def test_clasifica_y_pasa_temperatura(self):
        cliente = MagicMock()
        cliente.clasificar.return_value = "Proyecto A"
        with patch.object(gantt, "obtener_proyectos", return_value=self._proyectos()), \
             patch.object(gantt, "get_cliente", return_value=cliente):
            resultado = gantt.clasificar_actividad("Ventana", "Actividad", 5)
        self.assertEqual(resultado, "Proyecto A")
        kwargs = cliente.clasificar.call_args.kwargs
        # promedio (0.1+0.3)/2 = 0.2
        self.assertAlmostEqual(kwargs["temperature"], 0.2, places=3)

    def test_prompt_tiene_bloques(self):
        cliente = MagicMock()
        cliente.clasificar.return_value = "Proyecto A"
        with patch.object(gantt, "obtener_proyectos", return_value=self._proyectos()), \
             patch.object(gantt, "get_cliente", return_value=cliente):
            gantt.clasificar_actividad("Ventana", "Actividad", 5)
        prompt = cliente.clasificar.call_args.args[0]
        self.assertIn("DESCRIPCIÓN:", prompt)
        self.assertIn("OBJETIVOS ESPECÍFICOS:", prompt)
        self.assertIn("Desc A", prompt)
        self.assertIn("Obj A", prompt)

    def test_actividad_corta_no_clasifica(self):
        with patch.object(gantt, "obtener_proyectos", return_value=self._proyectos()), \
             patch.object(gantt, "get_cliente") as mock_get:
            self.assertIsNone(gantt.clasificar_actividad("a", "b", 1))
            mock_get.assert_not_called()

    def test_sin_proyectos_no_clasifica(self):
        with patch.object(gantt, "obtener_proyectos", return_value=[]), \
             patch.object(gantt, "get_cliente") as mock_get:
            self.assertIsNone(gantt.clasificar_actividad("a", "b", 5))
            mock_get.assert_not_called()

    def test_respuesta_ninguno_retorna_none(self):
        cliente = MagicMock()
        cliente.clasificar.return_value = "ninguno"
        with patch.object(gantt, "obtener_proyectos", return_value=self._proyectos()), \
             patch.object(gantt, "get_cliente", return_value=cliente):
            self.assertIsNone(gantt.clasificar_actividad("a", "b", 5))

    def test_retrocompatibilidad_palabras_clave(self):
        proyectos = [{"nombre": "Legacy", "palabras_clave": "kw vieja",
                      "estado": "activo"}]
        cliente = MagicMock()
        cliente.clasificar.return_value = "Legacy"
        with patch.object(gantt, "obtener_proyectos", return_value=proyectos), \
             patch.object(gantt, "get_cliente", return_value=cliente):
            resultado = gantt.clasificar_actividad("a", "b", 3)
        self.assertEqual(resultado, "Legacy")
        prompt = cliente.clasificar.call_args.args[0]
        self.assertIn("kw vieja", prompt)


class TestPersistenciaProyecto(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ruta_config = Path(self.tmpdir) / "config.json"
        self.ruta_config.write_text(
            json.dumps({"proyectos": []}), encoding="utf-8"
        )
        self._patcher = patch("gantt.Path")
        mock_path = self._patcher.start()

        def factory(arg):
            if str(arg).endswith("gantt.py"):
                m = MagicMock()
                m.parent = Path(self.tmpdir)
                return m
            return Path(arg)
        mock_path.side_effect = factory

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmpdir)

    def _leer(self, idx=0):
        cfg = json.loads(self.ruta_config.read_text(encoding="utf-8"))
        return cfg["proyectos"][idx]

    def test_agregar_persiste_estructura(self):
        gantt.agregar_proyecto("P", descripcion="d", objetivos="o", temperatura=0.4)
        p = self._leer()
        self.assertEqual(p["descripcion"], "d")
        self.assertEqual(p["objetivos"], "o")
        self.assertEqual(p["temperatura"], 0.4)

    def test_editar_elimina_legacy(self):
        # Crear uno con palabras_clave legacy directamente
        cfg = {"proyectos": [{"nombre": "P", "palabras_clave": "vieja",
                              "inicio": "2026-01-01", "fin": None, "estado": "activo"}]}
        self.ruta_config.write_text(json.dumps(cfg), encoding="utf-8")
        gantt.editar_proyecto(0, "P", "nueva desc", "obj", 0.2, "activo")
        p = self._leer()
        self.assertEqual(p["descripcion"], "nueva desc")
        self.assertNotIn("palabras_clave", p)

    def test_editar_no_afecta_otros(self):
        gantt.agregar_proyecto("P1", "d1", "o1", 0.1)
        gantt.agregar_proyecto("P2", "d2", "o2", 0.2)
        gantt.editar_proyecto(1, "P2", "d2", "o2", 0.9, "activo")
        self.assertEqual(self._leer(0)["temperatura"], 0.1)
        self.assertEqual(self._leer(1)["temperatura"], 0.9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
