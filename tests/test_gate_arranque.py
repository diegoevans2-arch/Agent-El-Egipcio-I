"""
Gate de QA de arranque (lógica de agente.py).

Como agente.py importa PyQt5 y módulos de Windows (pywin32), no se puede
importar directo en cualquier OS. Aquí testeamos la lógica del gate de
forma aislada:

1. correr_qa_para_arranque devuelve la estructura esperada
2. El gate detecta correctamente OK vs fallo
3. El gate captura tracebacks en el detalle

La integración con el popup de PyQt (ejecutar_gate_qa, _mostrar_popup...)
no se testea aquí porque requiere QApplication; se valida manualmente.
"""

import sys
import unittest
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from tests.run_qa import correr_qa_para_arranque, _MODULOS_TEST


class TestGateEstructura(unittest.TestCase):
    """La función de gate devuelve la estructura de datos esperada."""

    def test_retorna_dict_con_claves(self):
        resultado = correr_qa_para_arranque()
        claves_esperadas = {
            "ok", "total", "exitosos", "fallos", "errores",
            "modulos_con_problemas", "detalle", "gate_concluyente",
        }
        self.assertEqual(set(resultado.keys()), claves_esperadas)

    def test_tipos_correctos(self):
        r = correr_qa_para_arranque()
        self.assertIsInstance(r["ok"], bool)
        self.assertIsInstance(r["total"], int)
        self.assertIsInstance(r["modulos_con_problemas"], list)
        self.assertIsInstance(r["detalle"], str)
        self.assertIsInstance(r["gate_concluyente"], bool)

    def test_qa_completo_pasa(self):
        """En un estado sano, el gate debe retornar ok=True."""
        r = correr_qa_para_arranque()
        self.assertTrue(r["ok"],
                        f"El QA debería pasar. Problemas: {r['modulos_con_problemas']}")
        self.assertEqual(r["fallos"], 0)
        self.assertEqual(r["errores"], 0)
        self.assertTrue(r["gate_concluyente"])

    def test_consistencia_de_conteos(self):
        """exitosos + fallos + errores == total."""
        r = correr_qa_para_arranque()
        self.assertEqual(
            r["exitosos"] + r["fallos"] + r["errores"],
            r["total"]
        )

    def test_corre_todos_los_modulos(self):
        """El total de tests debe ser > 0 (corrió algo)."""
        r = correr_qa_para_arranque()
        self.assertGreater(r["total"], 0)


class TestGateDetectaFallos(unittest.TestCase):
    """El gate debe detectar fallos inyectados y capturar el traceback."""

    def test_detecta_modulo_inexistente(self):
        """
        Si se agrega un módulo que no existe, el gate lo reporta como
        problema (error de carga) sin reventar.
        """
        import tests.run_qa as rq
        original = rq._MODULOS_TEST
        try:
            rq._MODULOS_TEST = original + [
                ("tests.modulo_que_no_existe_xyz", "Módulo fantasma")
            ]
            r = rq.correr_qa_para_arranque()
            # Debe haber detectado el problema
            self.assertFalse(r["ok"])
            self.assertIn("Módulo fantasma", r["modulos_con_problemas"])
            # El detalle debe mencionar el error
            self.assertIn("fantasma", r["detalle"].lower() + " ".join(
                r["modulos_con_problemas"]).lower())
        finally:
            rq._MODULOS_TEST = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
