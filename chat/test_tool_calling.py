
import json


def probar_tool_calling():

    # Importación dentro de la función.
    from groq_client import consultar_groq

    tools = [
        {
            "type": "function",
            "function": {
                "name": "buscar_pelicula",
                "description": "Busca información de una película por su nombre.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "titulo": {
                            "type": "string",
                            "description": "Nombre de la película."
                        }
                    },
                    "required": ["titulo"],
                    "additionalProperties": False
                }
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": """
            Eres PromptCorn, un asistente especializado en películas.
            Cuando el usuario solicite buscar información de una película,
            debes utilizar la herramienta buscar_pelicula.
            """
        },
        {
            "role": "user",
            "content": "Busca información de la película Interstellar."
        }
    ]

    try:
        respuesta = consultar_groq(messages, tools=tools)

        print("\nRESPUESTA DEL MODELO:\n")
        print(respuesta.content)

        if respuesta.tool_calls:
            for llamada in respuesta.tool_calls:
                nombre = llamada.function.name
                argumentos = json.loads(llamada.function.arguments)

                print("\nHERRAMIENTA SOLICITADA:")
                print("Función:", nombre)
                print("Argumentos:", argumentos)
        else:
            print("\nEl modelo respondió sin solicitar herramientas.")

    except Exception as error:
        print("\nERROR:")
        print(error)


if __name__ == "__main__":
    probar_tool_calling()
