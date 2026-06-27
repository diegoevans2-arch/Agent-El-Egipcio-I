"""
Proyectos (MOCs y migración) en proyectos.py.

Cubre:
1. _slugify: nombres de archivo válidos
2. crear_md_proyecto: estructura del .md con descripción y objetivos
3. ruta_md_proyecto: apunta a la carpeta correcta
4. _agrupar_rangos: agrupación de días consecutivos
5. _detectar_personas_proyecto: matching de personas conocidas
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

from tests.conftest import vault_temporal, config_minima
import proyectos
import utils


class TestSlugify(unittest.TestCase):

    def test_espacios_a_underscore(self):
        slug = proyectos._slugify("Maestro Mallas")
        self.assertNotIn(" ", slug)

    def test_sin_caracteres_invalidos(self):
        slug = proyectos._slugify("Proyecto / con \\ chars : raros")
        for char in ["/", "\\", ":"]:
            self.assertNotIn(char, slug)

    def test_no_vacio(self):
        self.assertTrue(len(proyectos._slugify("X")) > 0)


class TestCrearMdProyecto(unittest.TestCase):

    def test_crea_md_con_estructura(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config), \
                 patch.object(proyectos, "cargar_config", return_value=config):
                ruta = proyectos.crear_md_proyecto(
                    "Mi Proyecto", descripcion="Una descripción",
                    objetivos="Unos objetivos"
                )
                self.assertTrue(ruta.exists())
                contenido = ruta.read_text(encoding="utf-8")
                # Debe contener las secciones clave
                self.assertIn("Mi Proyecto", contenido)
                self.assertIn("Una descripción", contenido)
                self.assertIn("Unos objetivos", contenido)
                # Frontmatter
                self.assertIn("proyecto: Mi Proyecto", contenido)
                # Gantt
                self.assertIn("gantt", contenido.lower())

    def test_no_sobrescribe_existente(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config), \
                 patch.object(proyectos, "cargar_config", return_value=config):
                ruta1 = proyectos.crear_md_proyecto("P", "desc original", "obj")
                # Modificar el archivo
                ruta1.write_text("CONTENIDO MODIFICADO", encoding="utf-8")
                # Volver a crear no debe sobrescribir
                ruta2 = proyectos.crear_md_proyecto("P", "otra desc", "otro obj")
                self.assertEqual(ruta1, ruta2)
                self.assertEqual(ruta2.read_text(encoding="utf-8"),
                                 "CONTENIDO MODIFICADO")

    def test_ruta_en_carpeta_proyectos(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config), \
                 patch.object(proyectos, "cargar_config", return_value=config):
                ruta = proyectos.ruta_md_proyecto("Test")
                # Debe estar dentro de proyectos/
                self.assertIn("proyectos", str(ruta))


class TestAgruparRangos(unittest.TestCase):

    def test_dias_consecutivos_se_agrupan(self):
        dias = ["2026-01-01", "2026-01-02", "2026-01-03"]
        rangos = proyectos._agrupar_rangos(dias)
        # 3 días consecutivos → 1 rango
        self.assertEqual(len(rangos), 1)

    def test_dias_separados_no_se_agrupan(self):
        dias = ["2026-01-01", "2026-01-10", "2026-01-20"]
        rangos = proyectos._agrupar_rangos(dias)
        self.assertEqual(len(rangos), 3)

    def test_lista_vacia(self):
        self.assertEqual(proyectos._agrupar_rangos([]), [])


class TestDetectarPersonas(unittest.TestCase):

    def test_detecta_persona_conocida(self):
        config = config_minima("/tmp/fake")
        # "Pablo Rubilar" está en personas_conocidas
        contenido = "Tuve una reunión con Pablo Rubilar sobre el proyecto."
        personas = proyectos._detectar_personas_proyecto(contenido, config)
        self.assertIn("Pablo Rubilar", personas)

    def test_no_detecta_si_falta_apellido(self):
        config = config_minima("/tmp/fake")
        # Solo "Pablo" sin apellido no debe matchear "Pablo Rubilar"
        contenido = "Hablé con Pablo ayer."
        personas = proyectos._detectar_personas_proyecto(contenido, config)
        self.assertNotIn("Pablo Rubilar", personas)

    def test_sin_personas_en_texto(self):
        config = config_minima("/tmp/fake")
        contenido = "Trabajé en queries SQL todo el día."
        personas = proyectos._detectar_personas_proyecto(contenido, config)
        self.assertEqual(personas, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
