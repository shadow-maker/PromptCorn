

import os
import json
import unittest

from types import SimpleNamespace
from unittest.mock import patch


# ==========================================================
# 1. CONFIGURACION DEL ENTORNO DE PRUEBAS
# ==========================================================

# Configurar variables antes de importar lambda_function.

os.environ["CONVERSATIONS_TABLE"] = "TestConversaciones"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["GROQ_API_KEY"] = "test-key-for-mocks"


from lambda_function import lambda_handler


# ==========================================================
# 2. RESPUESTA SIMULADA DE GROQ
# ==========================================================

class FakeGroqMessage:

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):

        resultado = {
            "role": "assistant",
            "content": self.content
        }

        if self.tool_calls:
            resultado["tool_calls"] = [
                {
                    "id": llamada.id,
                    "type": "function",
                    "function": {
                        "name": llamada.function.name,
                        "arguments": llamada.function.arguments
                    }
                }
                for llamada in self.tool_calls
            ]

        return resultado


# ==========================================================
# 3. PRUEBAS DEL BACKEND
# ==========================================================

class TestLambda(unittest.TestCase):

    # ------------------------------------------------------
    # PRUEBA 1: SOLICITUD INVALIDA
    # ------------------------------------------------------

    def test_solicitud_invalida(self):

        event = {
            "body": {
                "usuario_id": "",
                "mensaje": ""
            }
        }

        respuesta = lambda_handler(event, None)

        self.assertEqual(respuesta["statusCode"], 400)

        print("\nPRUEBA 1: Solicitud invalida - OK")


    # ------------------------------------------------------
    # PRUEBA 2: RESPUESTA SIN HERRAMIENTAS
    # ------------------------------------------------------

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion")
    @patch("lambda_function.consultar_groq")
    def test_respuesta_sin_herramientas(
        self,
        mock_groq,
        mock_historial,
        mock_guardar
    ):

        mock_historial.return_value = []

        mock_groq.return_value = FakeGroqMessage(
            content="Hola, soy PromptCorn. ¿Que pelicula buscas?",
            tool_calls=None
        )

        event = {
            "body": {
                "usuario_id": "usuario_001",
                "mensaje": "Hola"
            }
        }

        respuesta = lambda_handler(event, None)

        body = json.loads(respuesta["body"])

        self.assertEqual(respuesta["statusCode"], 200)

        self.assertEqual(
            body["respuesta"],
            "Hola, soy PromptCorn. ¿Que pelicula buscas?"
        )

        mock_groq.assert_called_once()

        print("\nPRUEBA 2: Respuesta sin herramientas - OK")


    # ------------------------------------------------------
    # PRUEBA 3: USO DEL HISTORIAL CONVERSACIONAL
    # ------------------------------------------------------

    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion")
    @patch("lambda_function.consultar_groq")
    def test_usa_historial_conversacion(
        self,
        mock_groq,
        mock_historial,
        mock_guardar
    ):

        mock_historial.return_value = [
            {
                "role": "user",
                "content": "Me gustan las peliculas de ciencia ficcion."
            },
            {
                "role": "assistant",
                "content": "Lo tendre en cuenta."
            }
        ]

        mock_groq.return_value = FakeGroqMessage(
            content="Te puedo recomendar Interstellar.",
            tool_calls=None
        )

        event = {
            "body": {
                "usuario_id": "usuario_001",
                "mensaje": "Recomiendame una pelicula"
            }
        }

        respuesta = lambda_handler(event, None)

        body = json.loads(respuesta["body"])

        self.assertEqual(respuesta["statusCode"], 200)

        self.assertEqual(
            body["respuesta"],
            "Te puedo recomendar Interstellar."
        )

        mensajes_enviados = mock_groq.call_args.args[0]

        self.assertIn(
            {
                "role": "user",
                "content": "Me gustan las peliculas de ciencia ficcion."
            },
            mensajes_enviados
        )

        self.assertIn(
            {
                "role": "assistant",
                "content": "Lo tendre en cuenta."
            },
            mensajes_enviados
        )

        mock_historial.assert_called_once_with("usuario_001")

        print("\nPRUEBA 3: Uso del historial conversacional - OK")


    # ------------------------------------------------------
    # PRUEBA 4: EJECUCION DE UNA HERRAMIENTA
    # ------------------------------------------------------

    @patch("lambda_function.ejecutar_herramienta")
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion")
    @patch("lambda_function.consultar_groq")
    def test_ejecucion_herramienta(
        self,
        mock_groq,
        mock_historial,
        mock_guardar,
        mock_ejecutor
    ):

        mock_historial.return_value = []

        llamada = SimpleNamespace(
            id="call_001",
            function=SimpleNamespace(
                name="buscar_pelicula",
                arguments=json.dumps({
                    "titulo": "Interstellar"
                })
            )
        )

        respuesta_tool = FakeGroqMessage(
            content=None,
            tool_calls=[llamada]
        )

        respuesta_final = FakeGroqMessage(
            content="Interstellar es una pelicula de 2014.",
            tool_calls=None
        )

        mock_groq.side_effect = [
            respuesta_tool,
            respuesta_final
        ]

        mock_ejecutor.return_value = {
            "titulo": "Interstellar",
            "anio": 2014,
            "director": "Christopher Nolan"
        }

        event = {
            "body": {
                "usuario_id": "usuario_001",
                "mensaje": "Busca Interstellar"
            }
        }

        respuesta = lambda_handler(event, None)

        body = json.loads(respuesta["body"])

        self.assertEqual(respuesta["statusCode"], 200)

        self.assertEqual(
            body["respuesta"],
            "Interstellar es una pelicula de 2014."
        )

        # Verificar ejecucion de la herramienta.
        # Las herramientas son de un solo usuario: no reciben usuario_id.
        mock_ejecutor.assert_called_once_with(
            "buscar_pelicula",
            {
                "titulo": "Interstellar"
            }
        )

        # Verificar dos consultas a Groq.
        self.assertEqual(mock_groq.call_count, 2)

        # Verificar que el resultado vuelva a Groq como tool.
        segundo_historial = mock_groq.call_args_list[1].args[0]

        mensajes_tool = [
            mensaje
            for mensaje in segundo_historial
            if mensaje.get("role") == "tool"
        ]

        self.assertEqual(len(mensajes_tool), 1)

        # Verificar que se guarde el mensaje del usuario.
        mock_guardar.assert_any_call(
            "usuario_001",
            "user",
            "Busca Interstellar"
        )

        # Verificar que se guarde la respuesta del asistente.
        mock_guardar.assert_any_call(
            "usuario_001",
            "assistant",
            "Interstellar es una pelicula de 2014."
        )

        # Deben guardarse exactamente dos mensajes.
        self.assertEqual(mock_guardar.call_count, 2)

        print("\nPRUEBA 4: Ejecucion de herramienta - OK")


    # ------------------------------------------------------
    # PRUEBA 4b: RECOMENDAR LLEGA AL LLM CON "SOLO ESTAS"
    # ------------------------------------------------------

    @patch("lambda_function.ejecutar_herramienta")
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion")
    @patch("lambda_function.consultar_groq")
    def test_recomendar_instruye_mostrar_solo_esas(
        self,
        mock_groq,
        mock_historial,
        mock_guardar,
        mock_ejecutor
    ):

        mock_historial.return_value = []

        def turno(cantidad):
            return FakeGroqMessage(content=None, tool_calls=[SimpleNamespace(
                id="call_rec",
                function=SimpleNamespace(
                    name="recomendar",
                    arguments=json.dumps({"orden": "reciente", "cantidad": cantidad})
                )
            )])

        mock_groq.side_effect = [
            turno(3), FakeGroqMessage(content="Iron Man 2 y Up."),
            turno(3), FakeGroqMessage(content="Nada cumple."),
        ]
        mock_ejecutor.side_effect = [
            {"modo": "perfil", "avisos": ["Solo 2 películas cumplen los filtros."],
             "recomendaciones": [
                 {"id": 1, "titulo": "Iron Man 2", "anio": 2010, "poster": "/a.jpg"},
                 {"id": 2, "titulo": "Up", "anio": 2009, "poster": "/b.jpg"}]},
            {"modo": "perfil", "avisos": [], "recomendaciones": []},
        ]

        def resultado_tool(llamada):
            historial = mock_groq.call_args_list[llamada].args[0]
            tool = [m for m in historial if m.get("role") == "tool"][-1]
            return json.loads(tool["content"])

        evento = {"body": {"usuario_id": "u", "mensaje": "Algo reciente"}}

        lambda_handler(evento, None)
        enviado = resultado_tool(1)
        self.assertIn("Muestra estas 2 películas y ninguna más", enviado["instruccion"])
        self.assertIn("ya vio", enviado["instruccion"])
        self.assertNotIn("poster", enviado["recomendaciones"][0])

        lambda_handler(evento, None)
        self.assertIn("no sugieras otras", resultado_tool(3)["instruccion"])

        print("\nPRUEBA 4b: recomendar instruye mostrar solo esas - OK")


    # ------------------------------------------------------
    # PRUEBA 5: ERROR EN LA EJECUCION DE UNA HERRAMIENTA
    # ------------------------------------------------------

    @patch("lambda_function.ejecutar_herramienta")
    @patch("lambda_function.guardar_mensaje")
    @patch("lambda_function.obtener_conversacion")
    @patch("lambda_function.consultar_groq")
    def test_error_herramienta(
        self,
        mock_groq,
        mock_historial,
        mock_guardar,
        mock_ejecutor
    ):

        mock_historial.return_value = []

        llamada = SimpleNamespace(
            id="call_error",
            function=SimpleNamespace(
                name="buscar_pelicula",
                arguments=json.dumps({
                    "titulo": "Interstellar"
                })
            )
        )

        respuesta_tool = FakeGroqMessage(
            content=None,
            tool_calls=[llamada]
        )

        respuesta_final = FakeGroqMessage(
            content="No pude consultar la pelicula en este momento.",
            tool_calls=None
        )

        mock_groq.side_effect = [
            respuesta_tool,
            respuesta_final
        ]

        mock_ejecutor.side_effect = RuntimeError(
            "API no disponible"
        )

        event = {
            "body": {
                "usuario_id": "usuario_001",
                "mensaje": "Busca Interstellar"
            }
        }

        respuesta = lambda_handler(event, None)

        body = json.loads(respuesta["body"])

        self.assertEqual(respuesta["statusCode"], 200)

        self.assertEqual(
            body["respuesta"],
            "No pude consultar la pelicula en este momento."
        )

        # Verificar que la herramienta fue llamada.
        mock_ejecutor.assert_called_once()

        # Verificar que Groq recibió el error de la herramienta.
        segundo_historial = mock_groq.call_args_list[1].args[0]

        mensajes_tool = [
            mensaje
            for mensaje in segundo_historial
            if mensaje.get("role") == "tool"
        ]

        self.assertEqual(len(mensajes_tool), 1)

        resultado_tool = json.loads(mensajes_tool[0]["content"])

        self.assertFalse(resultado_tool["ok"])

        print("\nPRUEBA 5: Error de herramienta - OK")


# ==========================================================
# 4. EJECUTAR TODAS LAS PRUEBAS
# ==========================================================

if __name__ == "__main__":

    unittest.main(verbosity=2)
