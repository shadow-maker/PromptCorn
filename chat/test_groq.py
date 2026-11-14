
from groq_client import consultar_groq

# Mensaje de prueba
messages = [
    {
        "role": "system",
        "content": """
        Eres PromptCorn, un asistente especializado
        en recomendaciones de películas.
        Responde siempre en español.
        """
    },
    {
        "role": "user",
        "content": "no se que ver, qué me sugieres?"
    }
]

try:
    respuesta = consultar_groq(messages)

    print("\nRESPUESTA DE PROMPTCORN:\n")
    print(respuesta.content)

except Exception as error:
    print("\nERROR AL CONECTAR CON GROQ:")
    print(error)
