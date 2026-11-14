
import json

from groq_client import consultar_groq
from system_prompt import SYSTEM_PROMPT
from conversation_memory import (
    obtener_conversacion,
    guardar_mensaje
)
from tools_handler import ejecutar_herramienta


# ==================================================
# 1. DEFINICION DE HERRAMIENTAS PARA GROQ
# ==================================================

TOOLS = [

    {
        "type": "function",
        "function": {
            "name": "recomendar",
            "description": "Recomendar peliculas segun los gustos del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genero": {
                        "type": "string",
                        "description": "Genero cinematografico preferido."
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Cantidad de peliculas a recomendar."
                    }
                },
                "required": [],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "buscar_pelicula",
            "description": "Buscar informacion de una pelicula por su titulo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Titulo de la pelicula."
                    }
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
            "description": "Consultar en que plataformas se puede ver una pelicula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identificador de la pelicula."
                    }
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
            "description": "Registrar que el usuario ha visto una pelicula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identificador de la pelicula."
                    }
                },
                "required": ["id"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "guardar_plataformas",
            "description": "Guardar las plataformas de streaming preferidas del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plataformas": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Lista de plataformas preferidas."
                    }
                },
                "required": ["plataformas"],
                "additionalProperties": False
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "obtener_historial",
            "description": "Consultar el historial de peliculas vistas por el usuario.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }
    }

]


# ==================================================
# 2. PROCESAMIENTO DE LA CONVERSACION
# ==================================================

def procesar_mensaje(user_id, mensaje):

    # Recuperar historial anterior
    historial = obtener_conversacion(user_id)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(historial)

    messages.append({
        "role": "user",
        "content": mensaje
    })

    # Guardar mensaje del usuario
    guardar_mensaje(user_id, "user", mensaje)

    # Limitar iteraciones para evitar ciclos infinitos
    for intento in range(5):

        respuesta = consultar_groq(
            messages,
            tools=TOOLS
        )

        # Si el modelo no solicita herramientas,
        # generar la respuesta final
        if not respuesta.tool_calls:

            contenido = respuesta.content or ""

            guardar_mensaje(
                user_id,
                "assistant",
                contenido
            )

            return contenido

        # Guardar la solicitud de herramientas del modelo
        messages.append(
            respuesta.model_dump(exclude_none=True)
        )

        # Ejecutar cada herramienta solicitada
        for tool_call in respuesta.tool_calls:

            nombre = tool_call.function.name

            try:

                argumentos = json.loads(
                    tool_call.function.arguments
                )

                # Validar que los argumentos sean un objeto
                if not isinstance(argumentos, dict):
                    raise ValueError(
                        "Los argumentos deben ser un objeto JSON."
                    )

                # Incorporar el user_id desde el backend
                # y no confiar en uno generado por el modelo
                argumentos["user_id"] = user_id

                # Ejecutar herramienta
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

            except Exception:

                resultado = {
                    "ok": False,
                    "error": "No se pudo ejecutar la herramienta."
                }

            # Devolver resultado a Groq
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    resultado,
                    ensure_ascii=False,
                    default=str
                )
            })

    return (
        "No pude completar la consulta. "
        "Por favor, intenta nuevamente."
    )


# ==================================================
# 3. FUNCION PRINCIPAL DE AWS LAMBDA
# ==================================================

def lambda_handler(event, context):

    try:

        # Obtener cuerpo de la solicitud
        body = event.get("body", event)

        # Si llega como texto, convertirlo a JSON
        if isinstance(body, str):
            body = json.loads(body)

        # Validar estructura
        if not isinstance(body, dict):
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "error": "El cuerpo debe ser un objeto JSON."
                })
            }

        # Obtener datos del usuario
        user_id = body.get("user_id")
        mensaje = body.get("message")

        # Validar campos obligatorios
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(mensaje, str)
            or not mensaje.strip()
        ):

            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "error": "user_id y message son obligatorios."
                })
            }

        user_id = user_id.strip()
        mensaje = mensaje.strip()

        # Procesar conversacion
        respuesta = procesar_mensaje(
            user_id,
            mensaje
        )

        # Respuesta exitosa
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "user_id": user_id,
                "response": respuesta
            }, ensure_ascii=False)
        }

    except json.JSONDecodeError:

        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "error": "El JSON recibido no es valido."
            })
        }

    except Exception:

        # No exponer detalles internos al usuario
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "error": "Error interno del servidor."
            })
        }
