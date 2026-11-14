
import json

from groq_client import consultar_groq
from system_prompt import SYSTEM_PROMPT
from conversation_memory import obtener_conversacion, guardar_mensaje
from tools_handler import ejecutar_herramienta


# ============================================================
# DEFINICIÓN DE HERRAMIENTAS PARA GROQ
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recomendar",
            "description": (
                "Recomienda películas según el género solicitado "
                "y la cantidad de resultados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "genero": {
                        "type": "string",
                        "description": "Género cinematográfico."
                    },
                    "limite": {
                        "type": "integer",
                        "description": "Cantidad máxima de películas."
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
            "description": "Busca una película por su título.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Título de la película."
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
            "description": (
                "Consulta las plataformas donde se puede ver "
                "una película."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identificador de la película."
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
            "description": "Registra una película como vista.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identificador de la película."
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
            "description": (
                "Guarda las plataformas de streaming preferidas "
                "del usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plataformas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de plataformas."
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
            "description": (
                "Obtiene el historial de películas vistas "
                "por el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }
    }
]


# ============================================================
# PROCESAMIENTO DEL MENSAJE CONVERSACIONAL
# ============================================================

def procesar_mensaje(user_id, mensaje):

    # Recuperar el historial de conversación del usuario.
    historial = obtener_conversacion(user_id)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    # Incorporar los mensajes anteriores.
    for item in historial:
        messages.append({
            "role": item["role"],
            "content": item["content"]
        })

    # Incorporar el mensaje actual.
    messages.append({
        "role": "user",
        "content": mensaje
    })

    # Guardar el mensaje del usuario.
    guardar_mensaje(user_id, "user", mensaje)

    # Máximo de iteraciones para evitar ciclos infinitos.
    max_intentos = 5

    for intento in range(max_intentos):

        respuesta = consultar_groq(
            messages,
            tools=TOOLS
        )

        # Si Groq no solicita herramientas, devolver respuesta.
        if not respuesta.tool_calls:

            contenido = respuesta.content or ""

            guardar_mensaje(
                user_id,
                "assistant",
                contenido
            )

            return contenido

        # Incorporar la respuesta de Groq con las llamadas
        # a herramientas al historial de mensajes.
        messages.append(
            respuesta.model_dump(exclude_none=True)
        )

        # Ejecutar cada herramienta solicitada por Groq.
        for tool_call in respuesta.tool_calls:

            nombre_herramienta = tool_call.function.name
            argumentos_json = tool_call.function.arguments

            try:
                argumentos = json.loads(argumentos_json)

                if not isinstance(argumentos, dict):
                    raise ValueError(
                        "Los argumentos deben ser un objeto JSON."
                    )

                # Incorporar el identificador del usuario.
                argumentos["user_id"] = user_id

                resultado = ejecutar_herramienta(
                    nombre_herramienta,
                    argumentos
                )

                contenido_resultado = json.dumps(
                    resultado,
                    ensure_ascii=False
                )

            except (ValueError, json.JSONDecodeError) as error:

                contenido_resultado = json.dumps({
                    "ok": False,
                    "error": (
                        "Los argumentos de la herramienta "
                        "no son válidos."
                    ),
                    "detalle": str(error)
                }, ensure_ascii=False)

            except Exception as error:

                contenido_resultado = json.dumps({
                    "ok": False,
                    "error": (
                        "No se pudo ejecutar la herramienta "
                        "solicitada."
                    ),
                    "detalle": str(error)
                }, ensure_ascii=False)

            # Devolver el resultado de la herramienta a Groq.
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": nombre_herramienta,
                "content": contenido_resultado
            })

    # Respuesta de seguridad si se alcanza el máximo de intentos.
    mensaje_final = (
        "Lo siento, no pude completar tu solicitud. "
        "¿Podrías intentarlo nuevamente?"
    )

    guardar_mensaje(
        user_id,
        "assistant",
        mensaje_final
    )

    return mensaje_final


# ============================================================
# HANDLER PRINCIPAL DE AWS LAMBDA
# ============================================================

def lambda_handler(event, context):

    # Encabezados comunes para todas las respuestas.
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": (
            "Content-Type, Authorization"
        ),
        "Access-Control-Max-Age": "86400"
    }

    try:

        # Detectar método HTTP en API Gateway v1 o v2.
        metodo = (
            event.get("httpMethod")
            or event.get("requestContext", {})
                 .get("http", {})
                 .get("method")
        )

        # Atender solicitudes preflight del navegador.
        if metodo == "OPTIONS":
            return {
                "statusCode": 200,
                "headers": headers,
                "body": ""
            }

        # Obtener el cuerpo de la solicitud.
        body = event.get("body", event)

        # API Gateway puede entregar el body como texto JSON.
        if isinstance(body, str):
            body = json.loads(body)

        # Validar que el cuerpo sea un objeto.
        if not isinstance(body, dict):
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "error": "El cuerpo debe ser un objeto JSON."
                }, ensure_ascii=False)
            }

        # Extraer datos de entrada.
        user_id = body.get("user_id")
        mensaje = body.get("message")

        # Validar campos obligatorios.
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(mensaje, str)
            or not mensaje.strip()
        ):
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "error": "user_id y message son obligatorios."
                }, ensure_ascii=False)
            }

        user_id = user_id.strip()
        mensaje = mensaje.strip()

        # Procesar la conversación.
        respuesta = procesar_mensaje(
            user_id,
            mensaje
        )

        # Respuesta exitosa.
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({
                "user_id": user_id,
                "response": respuesta
            }, ensure_ascii=False)
        }

    except json.JSONDecodeError:

        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({
                "error": "El JSON recibido no es válido."
            }, ensure_ascii=False)
        }

    except Exception:

        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({
                "error": "Error interno del servidor."
            }, ensure_ascii=False)
        }
