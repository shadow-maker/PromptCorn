
import os
from groq import Groq

# Validar que las variables de entorno existan
API_KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not API_KEY:
    raise ValueError(
        "No se encontró GROQ_API_KEY. Configúrala en PowerShell."
    )

# Crear cliente Groq
client = Groq(api_key=API_KEY)


def consultar_groq(messages, tools=None):
    """
    Envía una conversación a Groq.

    messages: historial de conversación.
    tools: herramientas disponibles para Tool Calling.
    """

    parametros = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_completion_tokens": 1024
    }

    if tools:
        parametros["tools"] = tools
        parametros["tool_choice"] = "auto"

    response = client.chat.completions.create(**parametros)

    # Devolvemos el mensaje completo para soportar Tool Calling
    return response.choices[0].message
