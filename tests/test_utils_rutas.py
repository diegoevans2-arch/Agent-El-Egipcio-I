"""
Rutas del vault en utils.py.

Verifica que cada helper de ruta:
1. Apunta a la subcarpeta correcta dentro de ruta_base
2. Crea la carpeta si no existe (mkdir idempotente)
3. Respeta crear=False (no crea cuando se pide solo la ruta)
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from tests.conftest import vault_temporal
import utils


class TestRutasVault(unittest.TestCase):

    def test_ruta_bitacoras(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_bitacoras()
            self.assertEqual(ruta, vault / "bitacoras")
            self.assertTrue(ruta.exists())

    def test_ruta_snippets(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_snippets()
            self.assertEqual(ruta, vault / "snippets")
            self.assertTrue(ruta.exists())

    def test_ruta_imagenes(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_imagenes()
            self.assertEqual(ruta, vault / "imagenes")
            self.assertTrue(ruta.exists())

    def test_ruta_proyectos(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_proyectos()
            self.assertEqual(ruta, vault / "proyectos")
            self.assertTrue(ruta.exists())

    def test_ruta_task(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_task()
            self.assertEqual(ruta, vault / "Task")
            self.assertTrue(ruta.exists())

    def test_ruta_scripts(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_scripts()
            self.assertEqual(ruta, vault / "scripts")
            self.assertTrue(ruta.exists())

    def test_ruta_solicitudes(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_solicitudes()
            self.assertEqual(ruta, vault / "Solicitudes")
            self.assertTrue(ruta.exists())

    def test_ruta_manuales_nombre_real(self):
        """La carpeta de manuales DEBE usar el nombre real con espacios."""
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_manuales()
            self.assertEqual(ruta, vault / "Manuales de Uso del Agente")
            self.assertTrue(ruta.exists())

    def test_crear_false_no_crea_carpeta(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta = utils.ruta_proyectos(crear=False)
            self.assertEqual(ruta, vault / "proyectos")
            self.assertFalse(ruta.exists())

    def test_mkdir_idempotente(self):
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta1 = utils.ruta_task()
                ruta2 = utils.ruta_task()
            self.assertEqual(ruta1, ruta2)
            self.assertTrue(ruta1.exists())

    def test_snippets_e_imagenes_en_raiz_no_dentro_de_bitacoras(self):
        """
        snippets/ e imagenes/ viven en la raíz del vault, NO dentro de
        bitacoras/. Este test fija esa decisión de estructura.
        """
        with vault_temporal() as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                ruta_snip = utils.ruta_snippets()
                ruta_img = utils.ruta_imagenes()
            # Están directamente bajo el vault
            self.assertEqual(ruta_snip.parent, vault)
            self.assertEqual(ruta_img.parent, vault)
            # NO están dentro de bitacoras/
            self.assertNotEqual(ruta_snip.parent.name, "bitacoras")
            self.assertNotEqual(ruta_img.parent.name, "bitacoras")

    def test_nombre_vault_deriva_de_ruta_base(self):
        """El nombre del vault se deriva del nombre de la carpeta raíz."""
        with vault_temporal(nombre_vault="Naos") as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                self.assertEqual(utils.nombre_vault(), "Naos")

    def test_nombre_vault_distinto(self):
        """Funciona con cualquier nombre de vault (no hardcodea 'Naos')."""
        with vault_temporal(nombre_vault="MiOtroVault") as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                self.assertEqual(utils.nombre_vault(), "MiOtroVault")

    def test_uri_obsidian_solo_vault(self):
        """Sin archivo, el URI abre solo el vault."""
        with vault_temporal(nombre_vault="Naos") as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                uri = utils.uri_obsidian()
            self.assertEqual(uri, "obsidian://open?vault=Naos")

    def test_uri_obsidian_con_archivo(self):
        """Con archivo, el URI incluye la ruta relativa."""
        with vault_temporal(nombre_vault="Naos") as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                uri = utils.uri_obsidian("bitacoras/bitacora_2026-06-26")
            self.assertIn("vault=Naos", uri)
            self.assertIn("bitacoras/bitacora_2026-06-26", uri)

    def test_uri_obsidian_no_hardcodea_bitacoras(self):
        """
        Regresión del bug: el URI NO debe decir 'vault=bitacoras'.
        Debe usar el nombre real del vault.
        """
        with vault_temporal(nombre_vault="Naos") as (vault, config):
            with patch.object(utils, "cargar_config", return_value=config):
                uri = utils.uri_obsidian("bitacoras/bitacora_x")
            self.assertNotIn("vault=bitacoras", uri)
            self.assertIn("vault=Naos", uri)


if __name__ == "__main__":
    unittest.main(verbosity=2)
