"""
Chat (contexto y keywords) en chat.py.

Cubre:
1. _detectar_archivos_task_solicitados: keywords de tipos de task
2. _detectar_pregunta_sobre_agente: keywords de manuales
3. _normalizar_texto: minúsculas + sin tildes
4. _cargar_manuales_agente: lectura de carpeta
5. _extraer_proyectos_mencionados: parsing de wikilinks de proyecto
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import chat


class TestNormalizarTexto(unittest.TestCase):

    def test_minusculas(self):
        self.assertEqual(chat._normalizar_texto("HOLA"), "hola")

    def test_sin_tildes(self):
        self.assertEqual(chat._normalizar_texto("decisión"), "decision")

    def test_vacio(self):
        self.assertEqual(chat._normalizar_texto(""), "")

    def test_none(self):
        self.assertEqual(chat._normalizar_texto(None), "")


class TestDetectarTasks(unittest.TestCase):

    def test_detecta_pendientes(self):
        tipos = chat._detectar_archivos_task_solicitados("¿qué pendientes tengo?")
        self.assertIn("pendiente", tipos)

    def test_detecta_decisiones(self):
        tipos = chat._detectar_archivos_task_solicitados("¿qué decisiones tomé?")
        self.assertIn("decision", tipos)

    def test_detecta_con_tildes(self):
        tipos = chat._detectar_archivos_task_solicitados("muéstrame mis decisiónes")
        self.assertIn("decision", tipos)

    def test_no_match_palabra_parcial(self):
        # "ideal" no debe matchear "idea"
        tipos = chat._detectar_archivos_task_solicitados("es la situación ideal")
        self.assertNotIn("idea", tipos)

    def test_pregunta_generica_sin_tasks(self):
        tipos = chat._detectar_archivos_task_solicitados("resume mi día")
        self.assertEqual(tipos, [])


class TestDetectarPreguntaAgente(unittest.TestCase):

    def test_temperatura(self):
        self.assertTrue(chat._detectar_pregunta_sobre_agente(
            "¿cómo funciona la temperatura?"))

    def test_configuracion(self):
        self.assertTrue(chat._detectar_pregunta_sobre_agente(
            "¿cómo configuro las listas?"))

    def test_el_egypcio(self):
        self.assertTrue(chat._detectar_pregunta_sobre_agente("¿qué es El Egypcio?"))

    def test_finops(self):
        self.assertTrue(chat._detectar_pregunta_sobre_agente(
            "¿cuánto cuesta el uso de api?"))

    def test_pregunta_trabajo_no_activa(self):
        self.assertFalse(chat._detectar_pregunta_sobre_agente(
            "¿cuánto tiempo dediqué a SQL?"))

    def test_pregunta_reunion_no_activa(self):
        self.assertFalse(chat._detectar_pregunta_sobre_agente(
            "resume la reunión con Pablo"))

    def test_vacio_y_none(self):
        self.assertFalse(chat._detectar_pregunta_sobre_agente(""))
        self.assertFalse(chat._detectar_pregunta_sobre_agente(None))


class TestCargarManuales(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ruta = Path(self.tmpdir) / "Manuales de Uso del Agente"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _patch(self):
        def fake(crear=True):
            if crear:
                self.ruta.mkdir(parents=True, exist_ok=True)
            return self.ruta
        return patch.object(chat, "ruta_manuales", side_effect=fake)

    def test_carpeta_vacia_placeholder(self):
        self.ruta.mkdir(parents=True, exist_ok=True)
        with self._patch():
            resultado = chat._cargar_manuales_agente()
        self.assertIn("vacía", resultado)

    def test_lee_archivos_md(self):
        self.ruta.mkdir(parents=True, exist_ok=True)
        (self.ruta / "manual.md").write_text("Contenido del manual", encoding="utf-8")
        with self._patch():
            resultado = chat._cargar_manuales_agente()
        self.assertIn("Contenido del manual", resultado)

    def test_ignora_no_md(self):
        self.ruta.mkdir(parents=True, exist_ok=True)
        (self.ruta / "x.txt").write_text("plano", encoding="utf-8")
        (self.ruta / "y.md").write_text("markdown", encoding="utf-8")
        with self._patch():
            resultado = chat._cargar_manuales_agente()
        self.assertIn("y.md", resultado)
        self.assertNotIn("x.txt", resultado)


class TestExtraerProyectos(unittest.TestCase):

    def test_extrae_proyecto_de_wikilink(self):
        # Formato: 🔗 **Proyecto:** [[slug|Nombre Proyecto]]
        contenido = "🔗 **Proyecto:** [[maestro-mallas|Maestro Mallas]]"
        proyectos = chat._extraer_proyectos_mencionados(contenido)
        self.assertIn("Maestro Mallas", proyectos)

    def test_sin_proyectos(self):
        contenido = "Texto sin wikilinks de proyecto."
        proyectos = chat._extraer_proyectos_mencionados(contenido)
        self.assertEqual(proyectos, [])

    def test_contenido_vacio(self):
        self.assertEqual(chat._extraer_proyectos_mencionados(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
