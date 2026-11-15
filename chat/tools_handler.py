
import os
import requests


# True: usa respuestas simuladas (mismo formato que las APIs reales).
# False: conecta con las APIs reales de Persona A.
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

# Todas las herramientas cuelgan de la misma HTTP API que el chat (serverless.yml),
# con una ruta POST /<herramienta>. Basta con la URL base.
# Opcional: una variable por herramienta para apuntar a otra URL.
TOOL_URLS = {
    "recomendar": "API_RECOMENDAR_URL",
    "buscar_pelicula": "API_BUSCAR_URL",
    "ver_donde_ver": "API_DONDE_VER_URL",
    "registrar_vista": "API_REGISTRAR_URL",
    "guardar_plataformas": "API_PLATAFORMAS_URL",
    "obtener_historial": "API_HISTORIAL_URL",
}


# ============================================================
# SIMULACIONES (formato de docs/contratos.md, ids reales del catálogo)
# ============================================================

_CATALOGO_DEMO = {
    8318: {"titulo": "Interestelar", "anio": 2014, "duracion_min": 169,
           "generos": ["Aventura", "Drama", "Ciencia ficción"],
           "plataformas": ["Prime Video", "HBO Max", "Claro Video"],
           "sinopsis": "Un grupo de astronautas cruza un agujero de gusano para buscarle un nuevo hogar a la humanidad."},
    1938: {"titulo": "Matrix", "anio": 1999, "duracion_min": 131,
           "generos": ["Acción", "Ciencia ficción"], "plataformas": ["HBO Max", "Claro Video"],
           "sinopsis": "Un hacker descubre que el mundo en que vive es una simulación y se une a la resistencia."},
    7332: {"titulo": "El Origen", "anio": 2010, "duracion_min": 148,
           "generos": ["Acción", "Ciencia ficción", "Crimen"], "plataformas": ["HBO Max"],
           "sinopsis": "Un ladrón que roba secretos desde los sueños recibe el encargo de implantar una idea."},
    8619: {"titulo": "Mad Max: Furia en el camino", "anio": 2015, "duracion_min": 120,
           "generos": ["Acción", "Aventura", "Ciencia ficción"],
           "plataformas": ["Prime Video", "Apple TV+", "HBO Max"],
           "sinopsis": "En un desierto postapocalíptico, Max y Furiosa huyen de un tirano en un camión de guerra."},
    9516: {"titulo": "Blade Runner 2049", "anio": 2017, "duracion_min": 164,
           "generos": ["Ciencia ficción", "Drama"], "plataformas": ["HBO Max"],
           "sinopsis": "Un agente replicante descubre un secreto que puede cambiar el orden de la sociedad."},
    1: {"titulo": "Toy Story", "anio": 1995, "duracion_min": 81,
        "generos": ["Familia", "Comedia", "Animación", "Aventura"], "plataformas": ["Disney+"],
        "sinopsis": "Un muñeco vaquero siente celos cuando llega un nuevo juguete espacial a la habitación."},
}

_TITULOS_EN_INGLES = {"interstellar": 8318, "inception": 7332, "the matrix": 1938,
                      "mad max: fury road": 8619}

_ALIAS_PLATAFORMAS = {
    "netflix": "Netflix", "prime video": "Prime Video", "amazon prime": "Prime Video",
    "amazon prime video": "Prime Video", "hbo": "HBO Max", "hbo max": "HBO Max", "max": "HBO Max",
    "disney+": "Disney+", "disney plus": "Disney+", "apple tv+": "Apple TV+", "paramount+": "Paramount+",
    "claro video": "Claro Video", "mubi": "Mubi", "mercado play": "Mercado Play",
}


def _id(argumentos):
    try:
        return int(argumentos.get("id"))
    except (TypeError, ValueError):
        return None


def _resumen(pid):
    p = _CATALOGO_DEMO[pid]
    return {"id": pid, **p, "poster": None}


def _ejecutar_mock(nombre, argumentos):

    if nombre == "recomendar":
        cantidad = int(argumentos.get("cantidad") or 3)
        generos = argumentos.get("generos") or []
        excluir = set(argumentos.get("excluir") or [])
        candidatas = [
            pid for pid in (8619, 1938, 9516, 7332, 8318, 1)
            if pid not in excluir
            and (not generos or set(generos) & set(_CATALOGO_DEMO[pid]["generos"]))
        ]
        return {
            "demo": True,
            "modo": "perfil",
            "recomendaciones": [
                {**_resumen(pid), "afinidad": 0.4,
                 "motivo": {"id": 8318, "titulo": "Interestelar", "calificacion": 5}}
                for pid in candidatas[:cantidad]
            ],
            "avisos": [] if candidatas else [
                "Ninguna película cumple todos los filtros: sugiere al usuario relajar alguno."],
        }

    if nombre == "buscar_pelicula":
        texto = str(argumentos.get("titulo", "")).lower().strip()
        resultados = [
            {"id": pid, "titulo": p["titulo"], "anio": p["anio"], "sinopsis": p["sinopsis"],
             "poster": None, "en_catalogo": True}
            for pid, p in _CATALOGO_DEMO.items()
            if texto and (texto in p["titulo"].lower() or _TITULOS_EN_INGLES.get(texto) == pid)
        ]
        if not resultados and "oppenheimer" in texto:
            resultados = [{"id": None, "titulo": "Oppenheimer", "anio": 2023,
                           "sinopsis": "La historia del físico que dirigió el proyecto de la bomba atómica.",
                           "poster": None, "en_catalogo": False}]
        return {"demo": True, "resultados": resultados[:5], "avisos": []}

    if nombre == "ver_donde_ver":
        pid = _id(argumentos)
        if pid not in _CATALOGO_DEMO:
            return {"demo": True, "ok": False, "status": 404, "error": "No existe una película con ese id."}
        p = _CATALOGO_DEMO[pid]
        return {"demo": True, "id": pid, "titulo": p["titulo"], "plataformas": p["plataformas"],
                "fecha": "2026-11-15", "avisos": []}

    if nombre == "registrar_vista":
        pid = _id(argumentos)
        if pid not in _CATALOGO_DEMO:
            return {"demo": True, "ok": False, "status": 404, "error": "No existe una película con ese id."}
        return {"demo": True, "ok": True, "id": pid, "titulo": _CATALOGO_DEMO[pid]["titulo"],
                "estado": argumentos.get("estado", "visto"),
                "calificacion": argumentos.get("calificacion")}

    if nombre == "guardar_plataformas":
        pedidas = argumentos.get("plataformas") or []
        canon = [_ALIAS_PLATAFORMAS.get(str(p).lower().strip()) for p in pedidas]
        return {"demo": True, "ok": True,
                "plataformas": list(dict.fromkeys(c for c in canon if c)),
                "no_reconocidas": [p for p, c in zip(pedidas, canon) if not c]}

    if nombre == "obtener_historial":
        return {"demo": True, "recomendaciones": [], "vistas": []}

    raise ValueError(f"Herramienta no reconocida: {nombre}")


# ============================================================
# EJECUCIÓN
# ============================================================

def _url(nombre):
    especifica = os.getenv(TOOL_URLS[nombre])
    if especifica:
        return especifica
    base = os.getenv("API_TOOLS_URL")
    if base:
        return f"{base.rstrip('/')}/{nombre}"
    raise ValueError(
        f"No se configuró API_TOOLS_URL (ni {TOOL_URLS[nombre]})."
    )


def ejecutar_herramienta(nombre, argumentos):

    if nombre not in TOOL_URLS:
        raise ValueError(f"Herramienta no reconocida: {nombre}")

    if not isinstance(argumentos, dict):
        raise ValueError("Los argumentos deben ser un diccionario.")

    # Modo de demostración: no requiere conexión con AWS ni APIs externas.
    if MOCK_MODE:
        return _ejecutar_mock(nombre, argumentos)

    # Modo real: API Gateway de las herramientas.
    url = _url(nombre)

    try:
        response = requests.post(
            url,
            json=argumentos,
            timeout=15
        )

        # 400/404: el body explica el problema (y a veces trae los valores
        # válidos). Se devuelve al LLM para que corrija y reintente.
        if response.status_code in (400, 404):
            try:
                return {"ok": False, "status": response.status_code, **response.json()}
            except ValueError:
                pass

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
