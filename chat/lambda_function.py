
import json

from groq_client import consultar_groq
from system_prompt import SYSTEM_PROMPT
from conversation_memory import obtener_conversacion, guardar_mensaje
from tools_handler import ejecutar_herramienta


# ============================================================
# DEFINICIÓN DE HERRAMIENTAS PARA GROQ (contrato: docs/contratos.md)
# ============================================================

GENEROS = [
    "Acción", "Animación", "Aventura", "Bélica", "Ciencia ficción", "Comedia",
    "Crimen", "Documental", "Drama", "Familia", "Fantasía", "Historia",
    "Misterio", "Música", "Película de TV", "Romance", "Suspenso", "Terror",
    "Western",
]

ID_PELICULA = {
    "type": "integer",
    "description": (
        "id de la película, tal como lo devolvió buscar_pelicula, "
        "recomendar u obtener_historial. Nunca lo inventes."
    )
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "recomendar",
            "description": (
                "Recomienda películas con el modelo de ML de PromptCorn. "
                "Ya conoce las notas, las películas vistas y las plataformas "
                "del usuario: solo pásale los filtros que el usuario pidió. "
                "Excluye sola lo visto y lo recomendado en las últimas 24 h, "
                "así que para 'dame otras opciones' basta con volver a llamarla."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cantidad": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Cuántas películas devolver (por defecto 3)."
                    },
                    "generos": {
                        "type": "array",
                        "items": {"type": "string", "enum": GENEROS},
                        "description": "Al menos uno de estos géneros."
                    },
                    "duracion_max": {
                        "type": "integer",
                        "description": "Duración máxima en minutos."
                    },
                    "anio_min": {
                        "type": "integer",
                        "description": "Año de estreno mínimo."
                    },
                    "anio_max": {
                        "type": "integer",
                        "description": "Año de estreno máximo."
                    },
                    "plataformas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Solo si el usuario pide plataformas distintas a "
                            "las suyas para esta consulta. [] = cualquiera."
                        )
                    },
                    "parecido_a": {
                        **ID_PELICULA,
                        "description": (
                            "id de una película para recomendar parecidas a "
                            "ella. Obténlo antes con buscar_pelicula."
                        )
                    },
                    "excluir": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "ids que no deben salir."
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
            "description": (
                "Busca una película por título (en español o inglés) y "
                "devuelve su id. Úsala antes de cualquier herramienta que "
                "necesite un id que aún no tienes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Título de la película."
                    },
                    "anio": {
                        "type": "integer",
                        "description": "Año de estreno, si el usuario lo dijo."
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
                "Plataformas de streaming en Perú donde se puede ver hoy "
                "una película (suscripción o gratis)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"id": ID_PELICULA},
                "required": ["id"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_vista",
            "description": (
                "Registra que el usuario vio una película (con su nota, que "
                "es lo que aprende el modelo) o que no le interesa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": ID_PELICULA,
                    "estado": {
                        "type": "string",
                        "enum": ["visto", "no_me_interesa"],
                        "description": "Por defecto visto."
                    },
                    "calificacion": {
                        "type": "number",
                        "minimum": 0.5,
                        "maximum": 5,
                        "description": "Nota de 0.5 a 5 (en medios puntos)."
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
                "Guarda las plataformas de streaming que tiene el usuario. "
                "Las recomendaciones se filtran por ellas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plataformas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Nombres de plataformas, p. ej. Netflix, Prime Video, HBO Max, Disney+."
                    },
                    "accion": {
                        "type": "string",
                        "enum": ["reemplazar", "agregar", "quitar"],
                        "description": "Por defecto reemplazar la lista completa."
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
                "Recomendaciones pasadas (con fecha, plataforma y motivo) "
                "y películas que el usuario registró como vistas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["recomendaciones", "vistas", "todo"],
                        "description": "Por defecto todo."
                    },
                    "limite": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Cuántas de cada tipo (por defecto 10)."
                    }
                },
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

                # Las herramientas son de un solo usuario (el fijo de la
                # app): no se les manda el user_id del chat.

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
