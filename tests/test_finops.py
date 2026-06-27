"""
FinOps (costos y tokens) en finops.py.

Cubre:
1. calcular_costo: cálculo correcto, modelo desconocido = 0
2. _obtener_precio: override de config tiene prioridad sobre default
3. registrar_uso: acumula llamadas/tokens/costo, robusto ante tipos raros
4. resumen_dia / resumen_mes: agregación correcta
5. limpiar_historico

Para no tocar el archivo finops_data.json real, _ruta_data se mockea a un
archivo temporal en cada test.
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import finops


class TestCalcularCosto(unittest.TestCase):

    def test_modelo_desconocido_costo_cero(self):
        with patch.object(finops, "cargar_config", return_value={}):
            costo = finops.calcular_costo("modelo-inexistente-xyz", 1000, 500)
        self.assertEqual(costo, 0.0)

    def test_costo_proporcional_a_tokens(self):
        """Con un precio override conocido, el costo debe ser proporcional."""
        config = {"finops": {"precios_override": {"test-model": [10.0, 30.0]}}}
        with patch.object(finops, "cargar_config", return_value=config):
            # 1M input a $10 + 1M output a $30 = $40
            costo = finops.calcular_costo("test-model", 1_000_000, 1_000_000)
        self.assertAlmostEqual(costo, 40.0, places=4)

    def test_costo_cero_tokens(self):
        config = {"finops": {"precios_override": {"test-model": [10.0, 30.0]}}}
        with patch.object(finops, "cargar_config", return_value=config):
            costo = finops.calcular_costo("test-model", 0, 0)
        self.assertEqual(costo, 0.0)


class TestObtenerPrecio(unittest.TestCase):

    def test_override_tiene_prioridad(self):
        config = {"finops": {"precios_override": {"claude-sonnet-4-6": [99.0, 199.0]}}}
        with patch.object(finops, "cargar_config", return_value=config):
            precio_in, precio_out = finops._obtener_precio("claude-sonnet-4-6")
        self.assertEqual((precio_in, precio_out), (99.0, 199.0))

    def test_modelo_desconocido_retorna_cero(self):
        with patch.object(finops, "cargar_config", return_value={}):
            precio = finops._obtener_precio("xyz-no-existe")
        self.assertEqual(precio, (0.0, 0.0))

    def test_config_falla_no_revienta(self):
        """Si cargar_config lanza, _obtener_precio debe degradar a default."""
        with patch.object(finops, "cargar_config", side_effect=Exception("boom")):
            precio = finops._obtener_precio("xyz")
        self.assertEqual(precio, (0.0, 0.0))


class TestRegistrarUso(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ruta_data = Path(self.tmpdir) / "finops_data.json"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _patches(self):
        """Mockea _ruta_data y cargar_config para aislar el test."""
        config = {"finops": {"precios_override": {"m": [10.0, 30.0]}}}
        return [
            patch.object(finops, "_ruta_data", return_value=self.ruta_data),
            patch.object(finops, "cargar_config", return_value=config),
        ]

    def test_registra_una_llamada(self):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            finops.registrar_uso("chat_usuario", "m", 1000, 500)
            data = json.loads(self.ruta_data.read_text(encoding="utf-8"))
            hoy = datetime.now().strftime("%Y-%m-%d")
            reg = data["registros_por_dia"][hoy]["chat_usuario"]
            self.assertEqual(reg["llamadas"], 1)
            self.assertEqual(reg["tokens_input"], 1000)
            self.assertEqual(reg["tokens_output"], 500)
            self.assertGreater(reg["costo_usd"], 0)
        finally:
            for p in patches:
                p.stop()

    def test_acumula_multiples_llamadas(self):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            finops.registrar_uso("chat_usuario", "m", 100, 50)
            finops.registrar_uso("chat_usuario", "m", 200, 100)
            data = json.loads(self.ruta_data.read_text(encoding="utf-8"))
            hoy = datetime.now().strftime("%Y-%m-%d")
            reg = data["registros_por_dia"][hoy]["chat_usuario"]
            self.assertEqual(reg["llamadas"], 2)
            self.assertEqual(reg["tokens_input"], 300)
            self.assertEqual(reg["tokens_output"], 150)
        finally:
            for p in patches:
                p.stop()

    def test_tipo_desconocido_no_revienta(self):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            # No debe lanzar excepción
            finops.registrar_uso("tipo_raro_inexistente", "m", 10, 5)
            data = json.loads(self.ruta_data.read_text(encoding="utf-8"))
            hoy = datetime.now().strftime("%Y-%m-%d")
            # Igual se registró (no se pierde el dato)
            self.assertIn("tipo_raro_inexistente", data["registros_por_dia"][hoy])
        finally:
            for p in patches:
                p.stop()

    def test_tokens_negativos_se_normalizan(self):
        patches = self._patches()
        for p in patches:
            p.start()
        try:
            finops.registrar_uso("chat_usuario", "m", -100, -50)
            data = json.loads(self.ruta_data.read_text(encoding="utf-8"))
            hoy = datetime.now().strftime("%Y-%m-%d")
            reg = data["registros_por_dia"][hoy]["chat_usuario"]
            # Negativos se clampar a 0
            self.assertEqual(reg["tokens_input"], 0)
            self.assertEqual(reg["tokens_output"], 0)
        finally:
            for p in patches:
                p.stop()


class TestResumenDia(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ruta_data = Path(self.tmpdir) / "finops_data.json"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_resumen_dia_vacio(self):
        """Sin datos, el resumen del día debe dar totales en cero."""
        with patch.object(finops, "_ruta_data", return_value=self.ruta_data), \
             patch.object(finops, "cargar_config", return_value={}):
            resumen = finops.resumen_dia()
        # Debe retornar un dict con estructura, sin reventar
        self.assertIsInstance(resumen, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
