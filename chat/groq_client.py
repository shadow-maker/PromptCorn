
import json
import os
from groq import Groq


# ==================================================
# 1. CONFIGURACION
# ==================================================

def _leer_api_key():
    """
    La key vive en SSM Parameter Store (SecureString); la variable
    GROQ_API_KEY_PARAM tiene el nombre del parámetro.
    GROQ_API_KEY directo queda para pruebas locales.
    """
    if os.getenv("GROQ_API_KEY"):
        return os.getenv("GROQ_API_KEY")
    parametro = os.getenv("GROQ_API_KEY_PARAM")
    if parametro:
        import boto3
        respuesta = boto3.client("ssm").get_parameter(
            Name=parametro,
            WithDecryption=True
        )
        return respuesta["Parameter"]["Value"]
    return None


API_KEY = _leer_api_key()

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

if not API_KEY:
    raise ValueError(
        "No se encontro la key de Groq. Configura GROQ_API_KEY_PARAM "
        "(parametro de SSM) o GROQ_API_KEY (pruebas locales)."
    )


# ==================================================
# 2. CREAR CLIENTE GROQ
# ==================================================

client = Groq(
    api_key=API_KEY,
    # La Lambda tiene 29 s (API Gateway corta a los 30): cada llamada a Groq
    # debe fallar rápido en vez de esperar reintentos largos por el límite
    # de tokens por minuto. lambda_function controla el presupuesto total.
    timeout=float(os.getenv("GROQ_TIMEOUT", "12")),
    max_retries=int(os.getenv("GROQ_MAX_RETRIES", "1"))
)


# ==================================================
# 3. FUNCION DE CONSULTA
# ==================================================

def consultar_groq(messages, tools=None):
    """
    Envia una conversacion a Groq.

    messages:
        Historial de mensajes de la conversacion.

    tools:
        Lista de herramientas disponibles para Tool Calling.

    Retorna:
        El mensaje generado por el modelo.
    """

    parametros = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_completion_tokens": 1024
    }

    # gpt-oss razona antes de responder y esos tokens cuentan para el limite
    # por minuto de Groq: con esfuerzo "low" gasta mucho menos.
    if MODEL.startswith("openai/gpt-oss"):
        parametros["extra_body"] = {
            "reasoning_effort": os.getenv("GROQ_REASONING_EFFORT", "low")
        }

    # Incorporar herramientas cuando esten disponibles
    if tools is not None:
        parametros["tools"] = tools
        parametros["tool_choice"] = "auto"

    # Consultar modelo
    response = client.chat.completions.create(
        **parametros
    )

    # Consumo de tokens en CloudWatch (para vigilar el límite por minuto de Groq)
    uso = getattr(response, "usage", None)
    if uso is not None:
        print(json.dumps({
            "tipo": "groq",
            "modelo": MODEL,
            "tokens_entrada": getattr(uso, "prompt_tokens", None),
            "tokens_salida": getattr(uso, "completion_tokens", None)
        }))

    # Devolver el mensaje completo:
    # puede contener texto o solicitudes de herramientas
    return response.choices[0].message
