
import os
from groq import Groq


# ==================================================
# 1. CONFIGURACION
# ==================================================

API_KEY = os.getenv("GROQ_API_KEY")

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

if not API_KEY:
    raise ValueError(
        "No se encontro GROQ_API_KEY. "
        "Configura la variable de entorno."
    )


# ==================================================
# 2. CREAR CLIENTE GROQ
# ==================================================

client = Groq(
    api_key=API_KEY,
    timeout=30.0,
    max_retries=2
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

    # Incorporar herramientas cuando esten disponibles
    if tools is not None:
        parametros["tools"] = tools
        parametros["tool_choice"] = "auto"

    # Consultar modelo
    response = client.chat.completions.create(
        **parametros
    )

    # Devolver el mensaje completo:
    # puede contener texto o solicitudes de herramientas
    return response.choices[0].message
