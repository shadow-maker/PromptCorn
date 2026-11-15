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
os.environ["DEPURAR"] = "1"

import lambda_function  # noqa: E402
from lambda_function import lambda_handler, para_llm  # noqa: E402


class RateLimitError(Exception):
    """Mismo nombre que la excepción de la librería groq."""


class BadRequestError(Exception):
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

    @patch("lambda_function.ejecutar_herramienta", return_value={"ok": True})
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    @patch("lambda_function.time")
    def test_presupuesto_de_tiempo(self, mock_time, mock_groq, *_):
        mock_time.time.side_effect = [0, 0, 20, 20, 20, 20]  # handler, inicio del turno, 2a vuelta: 20 s
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(name="registrar_vista", arguments='{"id": 1}'))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="nunca llega")]
        r = lambda_handler(evento("le doy un 4"), None)
        self.assertEqual(r["statusCode"], 200)
        self.assertIn("tardando", json.loads(r["body"])["respuesta"])
        self.assertEqual(mock_groq.call_count, 1)

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_reintenta_tool_use_failed(self, mock_groq, *_):
        mock_groq.side_effect = [BadRequestError("Error code: 400 - tool_use_failed"), FakeMensaje(content="ok")]
        r = lambda_handler(evento("vi iron man"), None)
        self.assertEqual(json.loads(r["body"])["respuesta"], "ok")
        self.assertEqual(mock_groq.call_count, 2)

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq", side_effect=ValueError("algo raro"))
    def test_detalle_del_error_solo_con_depurar(self, *_):
        contexto = SimpleNamespace(aws_request_id="req-123")
        con_depurar = {"body": json.dumps({"usuario_id": "u1", "mensaje": "hola", "depurar": True})}
        r = lambda_handler(evento("hola"), contexto)
        body = json.loads(r["body"])
        self.assertNotIn("detalle", body)
        self.assertEqual(body["id_solicitud"], "req-123")
        r = lambda_handler(con_depurar, contexto)
        self.assertIn("ValueError: algo raro", json.loads(r["body"])["detalle"])
        # si el servidor no habilita la depuración, el cliente no puede activarla
        with patch.dict(os.environ, {"DEPURAR": "0"}):
            r = lambda_handler(con_depurar, contexto)
            self.assertNotIn("detalle", json.loads(r["body"]))

    def test_parametros_opcionales_admiten_null(self):
        buscar = next(h for h in lambda_function.TOOLS if h["function"]["name"] == "buscar_pelicula")
        props = buscar["function"]["parameters"]["properties"]
        self.assertEqual(props["anio"]["type"], ["integer", "null"])
        self.assertEqual(props["titulo"]["type"], "string")  # obligatorio: sin null
        registrar = next(h for h in lambda_function.TOOLS if h["function"]["name"] == "registrar_vista")
        self.assertIn(None, registrar["function"]["parameters"]["properties"]["estado"]["enum"])

    @patch("lambda_function.ejecutar_herramienta", return_value={"resultados": []})
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_quita_nulls_antes_de_llamar(self, mock_groq, _o, _g, mock_herramienta):
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(
            name="buscar_pelicula", arguments='{"titulo": "Iron Man", "anio": null}'))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="ok")]
        lambda_handler(evento("vi iron man"), None)
        mock_herramienta.assert_called_once_with("buscar_pelicula", {"titulo": "Iron Man"})

    RECS = {"modo": "perfil", "recomendaciones": [
        {"id": 7, "titulo": "Matrix", "anio": 1999, "poster": "/m.jpg", "sinopsis": "x"},
        {"id": 8, "titulo": "Sin póster", "anio": None, "poster": None, "sinopsis": "y"}]}

    @patch("lambda_function.ejecutar_herramienta", return_value=RECS)
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_devuelve_peliculas_con_poster_url(self, mock_groq, *_):
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(name="recomendar", arguments="{}"))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="listo")]
        body = json.loads(lambda_handler(evento("algo"), None)["body"])
        self.assertEqual(body["peliculas"], [
            {"id": 7, "titulo": "Matrix", "anio": 1999, "poster_url": "https://image.tmdb.org/t/p/w342/m.jpg"},
            {"id": 8, "titulo": "Sin póster", "anio": None, "poster_url": None}])
        # el LLM no recibe el póster
        tool_msg = [m for m in mock_groq.call_args_list[1].args[0] if m.get("role") == "tool"][0]
        self.assertNotIn("poster", tool_msg["content"])

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_sin_recomendar_peliculas_vacio(self, mock_groq, *_):
        mock_groq.side_effect = [FakeMensaje(content="hola")]
        body = json.loads(lambda_handler(evento("hola"), None)["body"])
        self.assertEqual(body["peliculas"], [])

    @patch("lambda_function.ejecutar_herramienta", return_value={"modo": "perfil", "recomendaciones": []})
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion", return_value=[])
    @patch("lambda_function.consultar_groq")
    def test_limita_cantidad_a_5(self, mock_groq, _o, _g, mock_herramienta):
        llamada = SimpleNamespace(id="c1", function=SimpleNamespace(name="recomendar", arguments='{"cantidad": 9}'))
        mock_groq.side_effect = [FakeMensaje(tool_calls=[llamada]), FakeMensaje(content="ok")]
        lambda_handler(evento("dame 9"), None)
        mock_herramienta.assert_called_once_with("recomendar", {"cantidad": 5})


if __name__ == "__main__":
    unittest.main()
