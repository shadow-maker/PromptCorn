
import os
import requests


# True: usa respuestas simuladas.
# False: conecta con las APIs reales de Persona A.
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"


TOOL_URLS = {
    "recomendar": "API_RECOMENDAR_URL",
    "buscar_pelicula": "API_BUSCAR_URL",
    "ver_donde_ver": "API_DONDE_VER_URL",
    "registrar_vista": "API_REGISTRAR_URL",
    "guardar_plataformas": "API_PLATAFORMAS_URL",
    "obtener_historial": "API_HISTORIAL_URL",
}


def _ejecutar_mock(nombre, argumentos):

    if nombre == "recomendar":
        return {
            "modo": "demo",
            "recomendaciones": [
                {
                    "titulo": "Interstellar",
                    "genero": "Ciencia ficción",
                    "motivo": "Exploración espacial y viajes en el tiempo."
                },
                {
                    "titulo": "The Matrix",
                    "genero": "Ciencia ficción",
                    "motivo": "Realidad virtual e inteligencia artificial."
                },
                {
                    "titulo": "Arrival",
                    "genero": "Ciencia ficción",
                    "motivo": "Contacto extraterrestre y lenguaje."
                }
            ][:argumentos.get("limite", 3)]
        }

    if nombre == "buscar_pelicula":
        titulo = argumentos.get("titulo", "")

        peliculas_demo = {
            "interstellar": {
                "id": "demo_interstellar",
                "titulo": "Interstellar",
                "año": 2014
            },
            "the matrix": {
                "id": "demo_matrix",
                "titulo": "The Matrix",
                "año": 1999
            },
            "arrival": {
                "id": "demo_arrival",
                "titulo": "Arrival",
                "año": 2016
            }
        }

        pelicula = peliculas_demo.get(titulo.lower().strip())

        if pelicula:
            return {
                "modo": "demo",
                **pelicula,
                "mensaje": "Información cinematográfica simulada."
            }

        return {
            "modo": "demo",
            "mensaje": "Película no encontrada en la base de demostración.",
            "titulo_buscado": titulo
        }


    if nombre == "ver_donde_ver":
        return {
            "modo": "demo",
            "pelicula_id": argumentos.get("id"),
            "plataformas": ["Netflix", "Prime Video"],
            "mensaje": "Disponibilidad de ejemplo; no representa datos reales."
        }

    if nombre == "registrar_vista":
        return {
            "modo": "demo",
            "registrado": True,
            "pelicula_id": argumentos.get("id"),
            "mensaje": "Registro simulado correctamente."
        }

    if nombre == "guardar_plataformas":
        return {
            "modo": "demo",
            "guardado": True,
            "plataformas": argumentos.get("plataformas", []),
            "mensaje": "Plataformas guardadas de forma simulada."
        }

    if nombre == "obtener_historial":
        return {
            "modo": "demo",
            "historial": [],
            "mensaje": "Historial de demostración vacío."
        }

    raise ValueError(f"Herramienta no reconocida: {nombre}")


def ejecutar_herramienta(nombre, argumentos):

    if nombre not in TOOL_URLS:
        raise ValueError(f"Herramienta no reconocida: {nombre}")

    if not isinstance(argumentos, dict):
        raise ValueError("Los argumentos deben ser un diccionario.")

    # Modo de demostración: no requiere conexión con AWS ni APIs externas.
    if MOCK_MODE:
        return _ejecutar_mock(nombre, argumentos)

    # Modo real: utiliza las URLs configuradas en las variables de entorno.
    variable_url = TOOL_URLS[nombre]
    url = os.getenv(variable_url)

    if not url:
        raise ValueError(
            f"No se configuró la variable de entorno {variable_url}."
        )

    try:
        response = requests.post(
            url,
            json=argumentos,
            timeout=15
        )

        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            raise ValueError(
                f"La API de {nombre} no devolvió una respuesta JSON válida."
            )

    except requests.exceptions.Timeout:
        raise RuntimeError(f"Tiempo de espera agotado al ejecutar {nombre}.")

    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"No se pudo conectar con la API de {nombre}.")

    except requests.exceptions.HTTPError as error:
        raise RuntimeError(f"Error HTTP en {nombre}: {error}")

    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"Error de comunicación en {nombre}: {error}")
