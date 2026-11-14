
def probar_conexion_groq():
    # Importación dentro de la función para evitar
    # inicializar el cliente durante unittest discover.
    from groq_client import consultar_groq

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
            "content": "No sé qué ver, ¿qué me sugieres?"
        }
    ]

    try:
        respuesta = consultar_groq(messages)

        print("\nRESPUESTA DE PROMPTCORN:\n")
        print(respuesta.content)

    except Exception as error:
        print("\nERROR AL CONECTAR CON GROQ:")
        print(error)


if __name__ == "__main__":
    probar_conexion_groq()
