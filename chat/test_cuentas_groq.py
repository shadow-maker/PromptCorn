"""Pruebas de la rotación entre dos cuentas de Groq (sin red)."""
import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class RateLimitError(Exception):
    """Mismo nombre que la excepción de la librería groq."""

    def __init__(self, espera=None):
        super().__init__("429")
        self.response = SimpleNamespace(headers={"retry-after": espera} if espera else {})


class ClienteFalso:
    def __init__(self, nombre, falla=False):
        self.nombre, self.falla, self.llamadas = nombre, falla, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_):
        self.llamadas += 1
        if self.falla:
            raise RateLimitError("30")
        mensaje = SimpleNamespace(content=self.nombre, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensaje)], usage=None)


def cargar(**env):
    base = {"GROQ_API_KEY": "k1", "GROQ_API_KEY_2": "", "GROQ_ROTACION": "alternar"}
    with patch.dict(os.environ, {**base, **env}):
        import groq_client
        return importlib.reload(groq_client)


class TestCuentasGroq(unittest.TestCase):
    def test_una_cuenta_sigue_igual(self):
        g = cargar()
        self.assertEqual(len(g.clientes), 1)
        self.assertEqual([g.nuevo_turno() for _ in range(3)], [1, 1, 1])

    def test_dos_cuentas_se_alternan_por_mensaje(self):
        g = cargar(GROQ_API_KEY_2="k2")
        g.clientes[:] = [ClienteFalso("uno"), ClienteFalso("dos")]
        respuestas = []
        for _ in range(4):
            g.nuevo_turno()
            respuestas.append(g.consultar_groq([]).content)
        self.assertEqual(respuestas, ["uno", "dos", "uno", "dos"])

    def test_respaldo_usa_la_primera(self):
        g = cargar(GROQ_API_KEY_2="k2", GROQ_ROTACION="respaldo")
        self.assertEqual([g.nuevo_turno() for _ in range(3)], [1, 1, 1])

    def test_limite_pasa_a_la_otra_y_la_deja_descansar(self):
        g = cargar(GROQ_API_KEY_2="k2")
        g.clientes[:] = [ClienteFalso("uno", falla=True), ClienteFalso("dos")]
        g.nuevo_turno()
        self.assertEqual(g.consultar_groq([]).content, "dos")      # mismo mensaje, otra cuenta
        self.assertEqual(g.nuevo_turno(), 2)                        # le tocaba la 2
        self.assertEqual(g.nuevo_turno(), 2)                        # la 1 sigue descansando
        self.assertEqual(g.clientes[0].llamadas, 1)

    def test_las_dos_en_el_limite_da_el_error(self):
        g = cargar(GROQ_API_KEY_2="k2")
        g.clientes[:] = [ClienteFalso("uno", falla=True), ClienteFalso("dos", falla=True)]
        g.nuevo_turno()
        with self.assertRaises(RateLimitError):
            g.consultar_groq([])


if __name__ == "__main__":
    unittest.main()
