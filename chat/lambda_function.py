
import json
import time
import traceback

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

ID = {"type": "integer", "description": "id devuelto por otra herramienta."}


def _herramienta(nombre, descripcion, propiedades, requeridos=()):
    return {
        "type": "function",
        "function": {
            "name": nombre,
            "description": descripcion,
            "parameters": {
                "type": "object",
                "properties": propiedades,
                "required": list(requeridos),
                "additionalProperties": False
            }
        }
    }


TOOLS = [
    _herramienta(
        "recomendar",
        "Recomienda películas con el modelo de ML. Ya conoce notas, vistas y "
        "plataformas del usuario; pasa solo los filtros pedidos. No repite lo "
        "recomendado en 24 h.",
        {
            "cantidad": {"type": "integer", "minimum": 1, "maximum": 10,
                         "description": "Por defecto 3."},
            "generos": {"type": "array",
                        "items": {"type": "string", "enum": GENEROS}},
            "duracion_max": {"type": "integer", "description": "Minutos."},
            "anio_min": {"type": "integer"},
            "anio_max": {"type": "integer"},
            "plataformas": {"type": "array", "items": {"type": "string"},
                            "description": "Solo si pide otras distintas a las suyas; [] = cualquiera."},
            "parecido_a": {"type": "integer",
                           "description": "id de una película para recomendar parecidas."},
            "orden": {"type": "string", "enum": ["relevancia", "reciente"],
                      "description": "reciente = las más nuevas entre las afines."},
            "excluir": {"type": "array", "items": {"type": "integer"}}
        }
    ),
    _herramienta(
        "buscar_pelicula",
        "Busca una película por título (español o inglés) y devuelve su id.",
        {"titulo": {"type": "string"},
         "anio": {"type": "integer", "description": "Si el usuario lo dijo."}},
        ["titulo"]
    ),
    _herramienta(
        "ver_donde_ver",
        "Plataformas de Perú donde está hoy una película.",
        {"id": ID},
        ["id"]
    ),
    _herramienta(
        "registrar_vista",
        "Registra una película vista (con nota, que es lo que aprende el modelo) "
        "o que no le interesa.",
        {"id": ID,
         "estado": {"type": "string", "enum": ["visto", "no_me_interesa"]},
         "calificacion": {"type": "number", "minimum": 0.5, "maximum": 5}},
        ["id"]
    ),
    _herramienta(
        "guardar_plataformas",
        "Guarda las plataformas de streaming del usuario.",
        {"plataformas": {"type": "array", "items": {"type": "string"}},
         "accion": {"type": "string", "enum": ["reemplazar", "agregar", "quitar"]}},
        ["plataformas"]
    ),
    _herramienta(
        "obtener_historial",
        "Recomendaciones pasadas y películas vistas.",
        {"tipo": {"type": "string", "enum": ["recomendaciones", "vistas", "todo"]},
         "limite": {"type": "integer", "minimum": 1, "maximum": 50}}
    ),
]


# ============================================================
# RESULTADOS COMPACTOS PARA EL LLM
# ============================================================

# Campos que el LLM no usa: se quitan para ahorrar tokens (Groq limita
# los tokens por minuto y cada vuelta de herramientas reenvía todo).
CAMPOS_SOLO_FRONTEND = {"poster", "afinidad"}
MAX_SINOPSIS_LLM = 160


def para_llm(valor):
    if isinstance(valor, dict):
        compacto = {}
        for clave, v in valor.items():
            if clave in CAMPOS_SOLO_FRONTEND:
                continue
            if clave == "sinopsis" and isinstance(v, str) and len(v) > MAX_SINOPSIS_LLM:
                v = v[:MAX_SINOPSIS_LLM].rsplit(" ", 1)[0] + "…"
            compacto[clave] = para_llm(v)
        return compacto
    if isinstance(valor, list):
        return [para_llm(v) for v in valor]
    return valor


# ============================================================
# PROCESAMIENTO DEL MENSAJE CONVERSACIONAL
# ============================================================

def procesar_mensaje(usuario_id, mensaje, traza=None):
    """
    traza: lista opcional donde se anota cada paso (llamadas a Groq y
    herramientas con argumentos y resultado) para depurar.
    """
    if traza is None:
        traza = []

    # Recuperar el historial de conversación del usuario.
    historial = obtener_conversacion(usuario_id)

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
    guardar_mensaje(usuario_id, "user", mensaje)

    # Máximo de iteraciones para evitar ciclos infinitos.
    max_intentos = 5

    for intento in range(max_intentos):

        respuesta = consultar_groq(
            messages,
            tools=TOOLS
        )

        traza.append({
            "paso": "groq",
            "vuelta": intento + 1,
            "pide_herramientas": [
                llamada.function.name for llamada in (respuesta.tool_calls or [])
            ]
        })

        # Si Groq no solicita herramientas, devolver respuesta.
        if not respuesta.tool_calls:

            contenido = respuesta.content or ""

            guardar_mensaje(
                usuario_id,
                "assistant",
                contenido
            )

            return contenido

        # Incorporar la respuesta de Groq con las llamadas
        # a herramientas al historial de mensajes (sin el razonamiento
        # del modelo: no hace falta reenviarlo y gasta tokens).
        mensaje_asistente = respuesta.model_dump(exclude_none=True)
        messages.append({
            clave: valor
            for clave, valor in mensaje_asistente.items()
            if clave in ("role", "content", "tool_calls")
        })

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
                # app): no se les manda el usuario_id del chat.

                resultado = ejecutar_herramienta(
                    nombre_herramienta,
                    argumentos
                )

                contenido_resultado = json.dumps(
                    para_llm(resultado),
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

            traza.append({
                "paso": "herramienta",
                "nombre": nombre_herramienta,
                "argumentos": argumentos_json,
                "resultado": contenido_resultado[:1500]
            })

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
        usuario_id,
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

    usuario_id = None

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
        usuario_id = body.get("usuario_id")
        mensaje = body.get("mensaje")

        # Validar campos obligatorios.
        if (
            not isinstance(usuario_id, str)
            or not usuario_id.strip()
            or not isinstance(mensaje, str)
            or not mensaje.strip()
        ):
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "error": "usuario_id y mensaje son obligatorios."
                }, ensure_ascii=False)
            }

        usuario_id = usuario_id.strip()
        mensaje = mensaje.strip()

        # Procesar la conversación (con traza para depurar).
        inicio = time.time()
        traza = []
        respuesta = procesar_mensaje(
            usuario_id,
            mensaje,
            traza
        )

        # Una línea JSON por turno en CloudWatch (serverless logs -f chat):
        # mensaje, herramientas usadas con argumentos y resultado, y duración.
        print(json.dumps({
            "tipo": "turno",
            "usuario_id": usuario_id,
            "mensaje": mensaje,
            "respuesta": respuesta[:2000],
            "traza": traza,
            "duracion_ms": int((time.time() - inicio) * 1000)
        }, ensure_ascii=False))

        # Respuesta exitosa.
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({
                "usuario_id": usuario_id,
                "respuesta": respuesta,
                # "depurar": true en el request devuelve la traza (pruebas sin acceso a CloudWatch)
                **({"traza": traza} if body.get("depurar") else {})
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

    except Exception as error:

        # Queda en CloudWatch (serverless logs -f chat).
        traceback.print_exc()

        # Límite de uso de Groq (tokens o pedidos por minuto): no es una
        # falla del sistema, se le pide al usuario que reintente.
        if type(error).__name__ == "RateLimitError":
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "usuario_id": usuario_id,
                    "respuesta": (
                        "Estoy atendiendo muchas consultas en este momento. "
                        "Dame unos segundos y vuelve a enviar tu mensaje, por favor."
                    ),
                    "reintentar": True
                }, ensure_ascii=False)
            }

        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({
                "error": "Error interno del servidor."
            }, ensure_ascii=False)
        }
