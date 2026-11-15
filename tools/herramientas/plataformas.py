"""Nombres de plataformas de streaming: una sola normalización para todo PromptCorn.

La usan la consolidación del catálogo (scripts/consolidar.py), `ver_donde_ver` (disponibilidad en vivo)
y `guardar_plataformas` (lo que escribe el usuario), así todos hablan de "Prime Video" y no de
"Amazon Prime Video" o "amazon prime".
"""
from __future__ import annotations

import re
import unicodedata

# Canales y variantes que se fusionan con la plataforma principal
SUFIJOS_CANAL = [" Amazon Channel", " Apple TV Channel", " Roku Premium Channel", " Standard with Ads",
                 " Basic with Ads", " with Ads"]
RENOMBRAR = {
    "VIX": "ViX", "ViX Premium": "ViX", "Max": "HBO Max", "Disney Plus": "Disney+",
    "Paramount Plus": "Paramount+", "Apple TV Plus": "Apple TV+", "Apple TV": "Apple TV+",
    "Amazon Prime Video": "Prime Video", "Claro video": "Claro Video", "MGM Plus": "MGM+",
    "MUBI": "Mubi",
}
EXCLUIR = {"JustWatch TV Beta"}
TIPOS_SUSCRIPCION = ("flatrate", "free", "ads")  # sin alquiler ni compra

# Cómo lo dice la gente -> nombre canónico (se compara sin tildes, mayúsculas ni signos)
ALIAS_USUARIO = {
    "amazon": "Prime Video", "amazon prime": "Prime Video", "prime": "Prime Video",
    "hbo": "HBO Max", "max": "HBO Max", "disney": "Disney+", "disney plus": "Disney+",
    "star": "Disney+", "star plus": "Disney+", "paramount": "Paramount+", "paramount plus": "Paramount+",
    "apple": "Apple TV+", "apple tv": "Apple TV+", "claro": "Claro Video", "universal": "Universal+",
    "universal plus": "Universal+", "mgm": "MGM+", "mgm plus": "MGM+", "pluto": "Pluto TV",
    "mercadolibre": "Mercado Play", "mercado libre": "Mercado Play", "directv": "DIRECTV GO",
    "movistar": "MovistarTV", "movistar tv": "MovistarTV", "sony": "Sony One",
}


def normalizar(nombre: str) -> str | None:
    """Nombre tal como lo trae la fuente de disponibilidad -> nombre canónico (None = se descarta)."""
    nombre = nombre.strip()
    if nombre in EXCLUIR:
        return None
    for s in SUFIJOS_CANAL:
        if nombre.lower().endswith(s.lower()):
            nombre = nombre[: -len(s)].strip()
    return RENOMBRAR.get(nombre, nombre)


def de_proveedores(proveedores: dict) -> list[str]:
    """{"flatrate": [{"nombre": ...}], "rent": [...], ...} -> plataformas canónicas por suscripción o gratis."""
    salida = []
    for tipo in TIPOS_SUSCRIPCION:
        for p in proveedores.get(tipo) or []:
            n = normalizar(p.get("nombre") or p.get("provider_name") or "")
            if n and n not in salida:
                salida.append(n)
    return salida


def _clave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    texto = texto.replace("+", " plus")
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def interpretar(texto: str, validas: list[str]) -> str | None:
    """Lo que escribió el usuario ("netflix", "Amazon Prime", "HBO") -> nombre canónico de `validas`, o None."""
    por_clave = {_clave(v): v for v in validas}
    clave = _clave(texto)
    if clave in por_clave:
        return por_clave[clave]
    alias = ALIAS_USUARIO.get(clave)
    if alias in validas:
        return alias
    normal = normalizar(texto)
    if normal and _clave(normal) in por_clave:
        return por_clave[_clave(normal)]
    return None
