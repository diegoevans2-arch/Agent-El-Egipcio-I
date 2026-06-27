"""
Temas visuales (paletas) en temas.py.

Verifica que:
1. Existen las 5 paletas esperadas
2. Cada paleta tiene TODAS las claves de color requeridas (consistencia)
3. Los valores son colores hex válidos
4. obtener_paleta / obtener_paleta_activa funcionan
5. El tema default es válido

El test de consistencia de claves es clave: si una paleta nueva omite una
clave de color, los stylesheets que la usan fallarían silenciosamente al
aplicar ese tema. Aquí lo atrapamos.
"""

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import temas

_RE_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class TestTemas(unittest.TestCase):

    def test_existen_cinco_paletas(self):
        self.assertEqual(len(temas.PALETAS), 5,
                         "Deben existir exactamente 5 paletas")

    def test_ids_validos_presentes(self):
        for tema_id in temas.IDS_VALIDOS:
            self.assertIn(tema_id, temas.PALETAS,
                          f"Falta la paleta '{tema_id}' en PALETAS")

    def test_consistencia_de_claves_entre_paletas(self):
        """
        Todas las paletas deben tener el MISMO conjunto de claves de color.
        Si una difiere, los stylesheets fallarían al aplicar ese tema.
        """
        # Tomamos las claves de la paleta default como referencia
        claves_referencia = set(temas.PALETAS[temas.ID_DEFAULT].keys())
        self.assertGreater(len(claves_referencia), 0,
                           "La paleta de referencia no tiene claves")

        for tema_id, paleta in temas.PALETAS.items():
            claves = set(paleta.keys())
            faltantes = claves_referencia - claves
            extra = claves - claves_referencia
            self.assertEqual(
                faltantes, set(),
                f"La paleta '{tema_id}' NO tiene las claves: {faltantes}"
            )
            self.assertEqual(
                extra, set(),
                f"La paleta '{tema_id}' tiene claves EXTRA: {extra}"
            )

    def test_valores_son_hex_validos(self):
        """Todos los valores de color deben ser hex de 6 dígitos."""
        for tema_id, paleta in temas.PALETAS.items():
            for clave, valor in paleta.items():
                self.assertRegex(
                    valor, _RE_HEX,
                    f"'{tema_id}.{clave}' = '{valor}' no es hex válido"
                )

    def test_claves_criticas_presentes(self):
        """Verifica que existen las claves de color más usadas."""
        criticas = [
            "fondo_principal", "fondo_secundario", "texto_principal",
            "acento", "exito", "peligro", "borde",
        ]
        for tema_id, paleta in temas.PALETAS.items():
            for clave in criticas:
                self.assertIn(clave, paleta,
                              f"Falta clave crítica '{clave}' en '{tema_id}'")

    def test_obtener_paleta_por_id(self):
        paleta = temas.obtener_paleta(temas.ID_MOCHA)
        self.assertIsInstance(paleta, dict)
        self.assertIn("fondo_principal", paleta)

    def test_obtener_paleta_id_invalido_cae_a_default(self):
        """Un ID inexistente debe retornar la paleta default, no romper."""
        paleta = temas.obtener_paleta("no_existe_xyz")
        # Debe retornar algo válido (la default)
        self.assertIsInstance(paleta, dict)
        self.assertIn("fondo_principal", paleta)

    def test_default_es_valido(self):
        self.assertIn(temas.ID_DEFAULT, temas.PALETAS)

    def test_obtener_paleta_activa_lee_config(self):
        """obtener_paleta_activa debe leer el tema de config."""
        with patch.object(temas, "obtener_id_activo", return_value=temas.ID_NORD):
            paleta = temas.obtener_paleta_activa()
        self.assertEqual(paleta, temas.PALETAS[temas.ID_NORD])

    def test_listar_temas_retorna_los_cinco(self):
        lista = temas.listar_temas()
        self.assertEqual(len(lista), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
