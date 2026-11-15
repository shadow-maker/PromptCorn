"""Cliente mínimo de la API de metadatos (búsqueda por título y disponibilidad en Perú). Solo urllib.

Token: SSM Parameter Store (TMDB_TOKEN_PARAM, SecureString) o variable TMDB_TOKEN (pruebas locales).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.themoviedb.org/3"
REGION = "PE"
TIMEOUT = 5  # s; si no responde, las herramientas usan el catálogo local


class ErrorExterno(Exception):
    """La API externa no respondió o respondió con error: usar el respaldo local."""


class ClienteTMDB:
    def __init__(self, token: str | None = None):
        self._token = token

    @property
    def token(self) -> str:
        if self._token is None:
            if os.environ.get("TMDB_TOKEN"):
                self._token = os.environ["TMDB_TOKEN"]
            elif os.environ.get("TMDB_TOKEN_PARAM"):
                import boto3
                r = boto3.client("ssm").get_parameter(Name=os.environ["TMDB_TOKEN_PARAM"], WithDecryption=True)
                self._token = r["Parameter"]["Value"]
            else:
                raise ErrorExterno("No hay token configurado (TMDB_TOKEN_PARAM).")
        return self._token

    def _get(self, ruta: str, **params) -> dict:
        url = f"{BASE}{ruta}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
            raise ErrorExterno(str(e)) from e

    def buscar(self, titulo: str, anio: int | None = None) -> list[dict]:
        """Resultados por relevancia: [{ref, titulo, anio, sinopsis, poster}]."""
        datos = self._get("/search/movie", query=titulo, year=anio, language="es-MX", region=REGION,
                          include_adult="false")
        return [
            {"ref": r["id"], "titulo": r.get("title") or r.get("original_title"),
             "anio": int(r["release_date"][:4]) if r.get("release_date") else None,
             "sinopsis": r.get("overview") or None, "poster": r.get("poster_path")}
            for r in datos.get("results") or []
        ]

    def proveedores(self, ref: int) -> dict:
        """{"flatrate": [{"nombre": ...}], "rent": [...], ...} en Perú."""
        datos = self._get(f"/movie/{ref}/watch/providers")
        pe = (datos.get("results") or {}).get(REGION) or {}
        return {tipo: [{"nombre": p["provider_name"]} for p in lista]
                for tipo, lista in pe.items() if isinstance(lista, list)}
