
import json
from groq_client import consultar_groq

# --------------------------------------------------
# 1. DEFINICIÓN DE LAS HERRAMIENTAS
# --------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_pelicula",
            "description": "Busca información de una película por su nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre de la película."
                    }
                },
                "required": ["nombre"],
                "additionalProperties": False
            }
        }
    }
]


# --------------------------------------------------
# 2. IMPLEMENTACIÓN DE LA FUNCIÓN PYTHON
# --------------------------------------------------

def buscar_pelicula(nombre):

    # Datos simulados para probar el flujo.
    # Luego se reemplazarán por una consulta a la API real.

    peliculas_demo = {
        "interstellar": {
            "titulo": "Interstellar",
            "anio": 2014,
            "director": "Christopher Nolan",
            "genero": ["Ciencia ficción", "Drama", "Aventura"],
            "descripcion": (
                "Un grupo de exploradores viaja por un agujero "
                "de gusano en busca de un nuevo hogar para la humanidad."
            ),
            "fuente": "Datos de demostración local"
        }
    }

    resultado = peliculas_demo.get(nombre.lower().strip())

    if resultado:
        return resultado

    return {
        "error": "No se encontró la película en la base de demostración.",
        "pelicula_buscada": nombre
    }


# --------------------------------------------------
# 3. REGISTRO DE HERRAMIENTAS DISPONIBLES
# --------------------------------------------------

FUNCIONES = {
    "buscar_pelicula": buscar_pelicula
}


# --------------------------------------------------
# 4. CONVERSACIÓN INICIAL
# --------------------------------------------------

messages = [
    {
        "role": "system",
        "content": """
        Eres PromptCorn, un asistente especializado en películas.

        Responde siempre en español.
        Utiliza las herramientas cuando necesites información.
        No inventes datos que no estén en los resultados recibidos.
        """
    },
    {
        "role": "user",
        "content": "Busca información de la película Interstellar."
    }
]


# --------------------------------------------------
# 5. CICLO DE EJECUCIÓN DEL AGENTE
# --------------------------------------------------

try:

    for intento in range(5):

        respuesta = consultar_groq(messages, tools=TOOLS)

        # Si el modelo no solicita herramientas, termina.
        if not respuesta.tool_calls:

            print("\nPROMPTCORN:\n")
            print(respuesta.content)
            break

        # Guardar la solicitud de herramientas del modelo.
        messages.append(
            respuesta.model_dump(exclude_none=True)
        )

        # Ejecutar cada herramienta solicitada.
        for llamada in respuesta.tool_calls:

            nombre_funcion = llamada.function.name

            argumentos = json.loads(
                llamada.function.arguments
            )

            print("\nHERRAMIENTA EJECUTADA:")
            print("Función:", nombre_funcion)
            print("Argumentos:", argumentos)

            funcion = FUNCIONES.get(nombre_funcion)

            if funcion:

                resultado = funcion(**argumentos)

            else:

                resultado = {
                    "error": "Herramienta no reconocida."
                }

            print("\nRESULTADO DE PYTHON:")
            print(json.dumps(resultado, indent=4, ensure_ascii=False))

            # Enviar el resultado al historial para que Groq lo procese.
            messages.append({
                "role": "tool",
                "tool_call_id": llamada.id,
                "content": json.dumps(
                    resultado,
                    ensure_ascii=False
                )
            })

    else:
        print("\nSe alcanzó el límite de iteraciones del agente.")

except Exception as error:

    print("\nERROR EN LA EJECUCIÓN:")
    print(error)
