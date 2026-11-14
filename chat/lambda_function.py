
import json

from groq_client import consultar_groq
from system_prompt import SYSTEM_PROMPT
from conversation_memory import (
    obtener_conversacion,
    guardar_mensaje
)
from tools_handler import ejecutar_herramienta


# Definicion inicial de herramientas para Groq.
# Ajustar los parametros a los contratos de Persona A.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recomendar",
            "description": "Recomendar peliculas al usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "genero": {"type": "string"},
                    "limite": {"type": "integer"}
                },
                "required": ["user_id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_pelicula",
            "description": "Buscar una pelicula por titulo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"}
                },
                "required": ["titulo"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ver_donde_ver",
            "description": "Consultar donde ver una pelicula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"}
                },
                "required": ["id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_vista",
            "description": "Registrar una pelicula vista.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "id": {"type": "string"}
                },
                "required": ["user_id", "id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_plataformas",
            "description": "Guardar plataformas preferidas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "plataformas": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["user_id", "plataformas"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_historial",
            "description": "Consultar peliculas vistas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"}
                },
                "required": ["user_id"],
                "additionalProperties": False
            }
        }
    }
]


def procesar_mensaje(user_id, mensaje):

    historial = obtener_conversacion(user_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    messages.extend(historial)

    messages.append({
        "role": "user",
        "content": mensaje
    })

    guardar_mensaje(user_id, "user", mensaje)

    # Maximo 4 iteraciones para evitar ciclos infinitos.
    for intento in range(4):

        respuesta = consultar_groq(messages, TOOLS)

        messages.append(respuesta.model_dump(exclude_none=True))

        # Groq no solicita ninguna herramienta.
        if not respuesta.tool_calls:
            contenido = respuesta.content or ""

            guardar_mensaje(
                user_id,
                "assistant",
                contenido
            )

            return contenido

        # Ejecutar las herramientas solicitadas.
        for tool_call in respuesta.tool_calls:

            nombre = tool_call.function.name

            try:
                argumentos = json.loads(
                    tool_call.function.arguments
                )

                # Validacion basica de argumentos JSON.
                if not isinstance(argumentos, dict):
                    raise ValueError(
                        "Los argumentos deben ser un objeto JSON"
                    )

                # Evitar que el modelo suplante al usuario.
                if "user_id" in argumentos:
                    argumentos["user_id"] = user_id

                resultado = ejecutar_herramienta(
                    nombre,
                    argumentos
                )

                resultado = {
                    "ok": True,
                    "data": resultado
                }

            except (ValueError, json.JSONDecodeError) as error:

                resultado = {
                    "ok": False,
                    "error": str(error)
                }

            except Exception as error:

                resultado = {
                    "ok": False,
                    "error": "No se pudo ejecutar la herramienta"
                }

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    resultado,
                    ensure_ascii=False,
                    default=str
                )
            })

    return "No pude completar la consulta. Intenta nuevamente."


def lambda_handler(event, context):

    try:
        body = event.get("body", event)

        if isinstance(body, str):
            body = json.loads(body)

        user_id = body.get("user_id")
        mensaje = body.get("message")

        if not user_id or not mensaje:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Falta user_id o message"
                })
            }

        respuesta = procesar_mensaje(
            user_id,
            mensaje
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "user_id": user_id,
                "response": respuesta
            }, ensure_ascii=False)
        }

    except Exception:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Error interno del servidor"
            })
        }
