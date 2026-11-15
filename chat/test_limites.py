import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("CONVERSATIONS_TABLE", "TestConversaciones")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("GROQ_API_KEY", "test-key-for-mocks")

import lambda_function  # noqa: E402
from lambda_function import lambda_handler, para_llm  # noqa: E402


class RateLimitError(Exception):
    """Mismo nombre que la excepción de la librería groq."""


class FakeMensaje:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content, "reasoning": "pensando mucho..."}
        if self.tool_calls:
            d["tool_calls"] = [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments}}
                               for c in self.tool_calls]
        return d


def evento(mensaje="hola"):
    return {"body": json.dumps({"usuario_id": "u1", "mensaje": mensaje})}


class TestLimites(unittest.TestCase):

    def test_para_llm_quita_campos_y_acorta_sinopsis(self):
        r = para_llm({"recomendaciones": [{"id": 1, "poster": "/p.jpg", "afinidad": 0.4,
                                           "sinopsis": "palabra " * 100}]})
        pelicula = r["recomendaciones"][0]
        self.assertNotIn("poster", pelicula)
        self.assertNotIn("afinidad", pelicula)
        self.assertLessEqual(len(pelicula["sinopsis"]), lambda_function.MAX_SINOPSIS_LLM + 1)

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq", side_effect=RateLimitError("429"))
    def test_limite_de_groq_responde_amable(self, *_):
        r = lambda_handler(evento(), None)
        body = json.loads(r["body"])
        self.assertEqual(r["statusCode"], 200)
        self.assertTrue(body["reintentar"])
        self.assertIn("unos segundos", body["respuesta"])

    @patch("lambda_function.ejecutar_herramienta", return_value={"ok": True})
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_no_reenvia_el_razonamiento(self, mock_groq, *_):
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(name="obtener_historial", arguments="{}"))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="listo")]
        lambda_handler(evento("historial"), None)
        segundo = mock_groq.call_args_list[1].args[0]
        asistente = [m for m in segundo if m.get("role") == "assistant"][0]
        self.assertNotIn("reasoning", asistente)
        self.assertIn("tool_calls", asistente)

    @patch("lambda_function.ejecutar_herramienta", return_value={"modo": "perfil", "recomendaciones": []})
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_depurar_devuelve_traza(self, mock_groq, *_):
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(name="recomendar", arguments='{"orden": "reciente"}'))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="listo")]
        r = lambda_handler({"body": json.dumps({"usuario_id": "u1", "mensaje": "algo nuevo", "depurar": True})}, None)
        traza = json.loads(r["body"])["traza"]
        herramientas = [p for p in traza if p["paso"] == "herramienta"]
        self.assertEqual(herramientas[0]["nombre"], "recomendar")
        self.assertIn("reciente", herramientas[0]["argumentos"])
        # sin depurar, la respuesta no trae la traza
        mock_groq.side_effect = [FakeMensaje(content="hola")]
        r = lambda_handler(evento("hola"), None)
        self.assertNotIn("traza", json.loads(r["body"]))


if __name__ == "__main__":
    unittest.main()
