
import os
import requests


# --------------------------------------------------
# 1. CONFIGURACIÓN DE LAS API
# --------------------------------------------------

TOOL_URLS = {
    "recomendar": os.getenv("API_RECOMENDAR_URL"),
    "buscar_pelicula": os.getenv("API_BUSCAR_URL"),
    "ver_donde_ver": os.getenv("API_DONDE_VER_URL"),
    "registrar_vista": os.getenv("API_REGISTRAR_URL"),
    "guardar_plataformas": os.getenv("API_PLATAFORMAS_URL"),
    "obtener_historial": os.getenv("API_HISTORIAL_URL")
}


# --------------------------------------------------
# 2. EJECUTOR GENERAL DE HERRAMIENTAS
# --------------------------------------------------

def ejecutar_herramienta(nombre, argumentos):

    # Verificar que la herramienta exista
    if nombre not in TOOL_URLS:
        raise ValueError(
            f"Herramienta no reconocida: {nombre}"
        )

    # Obtener URL correspondiente
    url = TOOL_URLS[nombre]

    # Verificar que tenga URL configurada
    if not url:
        raise ValueError(
            f"No existe una URL configurada para {nombre}"
        )

    try:

        # Enviar solicitud a la API
        response = requests.post(
            url,
            json=argumentos,
            timeout=15
        )

        # Detectar errores HTTP
        response.raise_for_status()

        # Convertir respuesta a JSON
        try:
            resultado = response.json()

        except ValueError:
            raise ValueError(
                f"La API {nombre} no devolvió una respuesta JSON válida."
            )

        return resultado

    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"La API {nombre} excedió el tiempo de espera."
        )

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"No se pudo establecer conexión con la API {nombre}."
        )

    except requests.exceptions.HTTPError as error:
        raise RuntimeError(
            f"Error HTTP en {nombre}: {error}"
        )
