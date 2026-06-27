"""
Cliente IA multi-proveedor en cliente_ia.py.

Cubre:
1. Construcción con cada proveedor (claude/openai/gemini) — mockeando el SDK
2. Validación de entradas (proveedor inválido, key vacía)
3. Modelos principal y rápido se asignan correctamente
4. clamp de temperatura en clasificar
5. Gestión del cliente global (set/get/hay_cliente_activo)
6. Extracción de tokens por proveedor

NOTA: _inicializar_sdk se mockea para no requerir SDKs reales ni claves.
Lo que se testea es la lógica del wrapper, no las llamadas reales a las APIs.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import cliente_ia
from cliente_ia import ClienteIA


class TestConstruccionCliente(unittest.TestCase):

    def test_proveedor_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            ClienteIA("proveedor_inexistente", "key")

    def test_key_vacia_lanza_error(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            with self.assertRaises(ValueError):
                ClienteIA("claude", "")

    def test_key_solo_espacios_lanza_error(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            with self.assertRaises(ValueError):
                ClienteIA("claude", "   ")

    def test_construye_claude(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("claude", "test-key")
        self.assertEqual(cliente.proveedor, "claude")
        self.assertTrue(cliente.modelo)
        self.assertTrue(cliente.modelo_rapido)

    def test_construye_openai(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("openai", "test-key")
        self.assertEqual(cliente.proveedor, "openai")

    def test_construye_gemini(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("gemini", "test-key")
        self.assertEqual(cliente.proveedor, "gemini")

    def test_modelo_custom_se_respeta(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("claude", "test-key", modelo="modelo-custom")
        self.assertEqual(cliente.modelo, "modelo-custom")

    def test_key_se_trimea(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("claude", "  test-key  ")
        self.assertEqual(cliente.api_key, "test-key")


class TestClasificarTemperatura(unittest.TestCase):
    """El clamp de temperatura en clasificar debe acotar a [0, 1]."""

    def _cliente_claude_mockeado(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("claude", "test-key")
        # Mockear el SDK interno para capturar la llamada
        cliente._sdk = MagicMock()
        respuesta_fake = MagicMock()
        respuesta_fake.content = [MagicMock(text="Proyecto X")]
        cliente._sdk.messages.create.return_value = respuesta_fake
        # Evitar registro FinOps
        cliente._registrar_uso_seguro = MagicMock()
        cliente._extraer_tokens_claude = MagicMock(return_value=(10, 5))
        return cliente

    def test_temperatura_alta_se_clampa(self):
        cliente = self._cliente_claude_mockeado()
        cliente.clasificar("prompt", temperature=5.0)
        kwargs = cliente._sdk.messages.create.call_args.kwargs
        self.assertLessEqual(kwargs.get("temperature", 1.0), 1.0)

    def test_temperatura_negativa_se_clampa(self):
        cliente = self._cliente_claude_mockeado()
        cliente.clasificar("prompt", temperature=-1.0)
        kwargs = cliente._sdk.messages.create.call_args.kwargs
        self.assertGreaterEqual(kwargs.get("temperature", 0.0), 0.0)

    def test_temperatura_none_no_se_pasa(self):
        cliente = self._cliente_claude_mockeado()
        cliente.clasificar("prompt", temperature=None)
        kwargs = cliente._sdk.messages.create.call_args.kwargs
        # Si es None, no debe incluirse el parámetro temperature
        self.assertNotIn("temperature", kwargs)

    def test_temperatura_valida_se_pasa(self):
        cliente = self._cliente_claude_mockeado()
        cliente.clasificar("prompt", temperature=0.3)
        kwargs = cliente._sdk.messages.create.call_args.kwargs
        self.assertAlmostEqual(kwargs.get("temperature"), 0.3, places=3)


class TestClienteGlobal(unittest.TestCase):

    def setUp(self):
        # Resetear el cliente global antes de cada test
        cliente_ia._cliente_global = None

    def tearDown(self):
        cliente_ia._cliente_global = None

    def test_get_sin_cliente_lanza_error(self):
        with self.assertRaises(RuntimeError):
            cliente_ia.get_cliente()

    def test_hay_cliente_activo_false_inicialmente(self):
        self.assertFalse(cliente_ia.hay_cliente_activo())

    def test_set_y_get_cliente(self):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            cliente = ClienteIA("claude", "test-key")
        cliente_ia.set_cliente(cliente)
        self.assertTrue(cliente_ia.hay_cliente_activo())
        self.assertIs(cliente_ia.get_cliente(), cliente)


class TestExtraccionTokens(unittest.TestCase):
    """Los extractores de tokens deben ser robustos ante respuestas raras."""

    def _cliente(self, proveedor):
        with patch.object(ClienteIA, "_inicializar_sdk"):
            return ClienteIA(proveedor, "test-key")

    def test_tokens_claude(self):
        cliente = self._cliente("claude")
        resp = MagicMock()
        resp.usage.input_tokens = 100
        resp.usage.output_tokens = 50
        tin, tout = cliente._extraer_tokens_claude(resp)
        self.assertEqual((tin, tout), (100, 50))

    def test_tokens_openai(self):
        cliente = self._cliente("openai")
        resp = MagicMock()
        resp.usage.prompt_tokens = 80
        resp.usage.completion_tokens = 40
        tin, tout = cliente._extraer_tokens_openai(resp)
        self.assertEqual((tin, tout), (80, 40))


if __name__ == "__main__":
    unittest.main(verbosity=2)
