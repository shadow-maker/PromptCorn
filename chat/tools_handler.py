
import os
import requests


TOOL_URLS = {
    "recomendar": os.getenv("API_RECOMENDAR_URL"),
    "buscar_pelicula": os.getenv("API_BUSCAR_URL"),
    "ver_donde_ver": os.getenv("API_DONDE_VER_URL"),
    "registrar_vista": os.getenv("API_REGISTRAR_URL"),
    "guardar_plataformas": os.getenv("API_PLATAFORMAS_URL"),
    "obtener_historial": os.getenv("API_HISTORIAL_URL")
}


def ejecutar_herramienta(nombre, argumentos):

    url = TOOL_URLS.get(nombre)

    if not url:
        raise ValueError(
            f"No existe una URL configurada para {nombre}"
        )

    response = requests.post(
        url,
        json=argumentos,
        timeout=15
    )

    response.raise_for_status()

    return response.json()
