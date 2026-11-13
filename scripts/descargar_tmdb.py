"""Descarga metadatos y disponibilidad (Perú) de cada película de MovieLens desde TMDB.

Lee data/raw/movielens/links.csv y guarda un JSON recortado por película en
data/raw/tmdb/{tmdbId}.json. Retoma donde se quedó (salta los ya descargados).

Token: variable TMDB_TOKEN o archivo ~/.config/promptcorn/tmdb_token (nunca en el repo).
Uso: .venv/bin/python -I scripts/descargar_tmdb.py [--workers 16]
"""
import argparse
import csv
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LINKS = RAIZ / "data" / "raw" / "movielens" / "links.csv"
DESTINO = RAIZ / "data" / "raw" / "tmdb"
ERRORES = RAIZ / "data" / "raw" / "tmdb_errores.json"
REEMPLAZOS = RAIZ / "data" / "raw" / "tmdb_reemplazos.json"  # ID eliminado -> ID vigente

BASE = "https://api.themoviedb.org/3/movie/{id}?language=es-MX&append_to_response=credits,watch/providers,translations"
IDIOMAS = {"es-MX", "es-ES", "en-US"}
REGION = "PE"
CAMPOS = [
    "id", "title", "original_title", "original_language", "overview", "tagline",
    "release_date", "runtime", "genres", "poster_path", "popularity",
    "vote_average", "vote_count", "adult", "softcore", "status", "origin_country",
]


def leer_token() -> str:
    token = os.environ.get("TMDB_TOKEN")
    if not token:
        archivo = Path.home() / ".config" / "promptcorn" / "tmdb_token"
        token = archivo.read_text().strip()
    return token


def recortar(d: dict) -> dict:
    """Se queda solo con lo necesario (la respuesta completa pesa ~200 KB por el elenco)."""
    out = {k: d.get(k) for k in CAMPOS}
    creditos = d.get("credits") or {}
    out["directores"] = [c["name"] for c in creditos.get("crew", []) if c.get("job") == "Director"]
    out["reparto"] = [c["name"] for c in sorted(creditos.get("cast", []), key=lambda c: c.get("order", 99))[:5]]
    traducciones = (d.get("translations") or {}).get("translations", [])
    out["traducciones"] = {
        f'{t["iso_639_1"]}-{t["iso_3166_1"]}': {"title": t["data"].get("title"), "overview": t["data"].get("overview")}
        for t in traducciones
        if f'{t["iso_639_1"]}-{t["iso_3166_1"]}' in IDIOMAS
    }
    proveedores = ((d.get("watch/providers") or {}).get("results") or {}).get(REGION, {})
    out["proveedores_pe"] = {
        tipo: [{"id": p["provider_id"], "nombre": p["provider_name"]} for p in lista]
        for tipo, lista in proveedores.items()
        if tipo != "link"
    }
    return out


def descargar(tmdb_id: int, token: str, intentos: int = 5) -> tuple[int, str]:
    url = BASE.format(id=tmdb_id)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                datos = json.load(r)
            (DESTINO / f"{tmdb_id}.json").write_text(json.dumps(recortar(datos), ensure_ascii=False))
            return tmdb_id, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return tmdb_id, "404"
            if e.code == 429 or e.code >= 500:
                time.sleep(int(e.headers.get("Retry-After", 2 ** i)))
                continue
            return tmdb_id, f"http {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            time.sleep(2 ** i)
            ultimo = str(e)
    return tmdb_id, f"falló: {ultimo if 'ultimo' in locals() else 'reintentos agotados'}"


def buscar_por_imdb(imdb_id: str | None, token: str) -> int | None:
    """Devuelve el ID vigente de una película a partir de su ID de IMDb (o None)."""
    if not imdb_id:
        return None
    url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resultados = json.load(r).get("movie_results") or []
    except urllib.error.URLError:
        return None
    return resultados[0]["id"] if resultados else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limite", type=int, default=0, help="solo los primeros N (prueba)")
    args = ap.parse_args()

    token = leer_token()
    DESTINO.mkdir(parents=True, exist_ok=True)
    with LINKS.open() as f:
        ids = sorted({int(float(r["tmdbId"])) for r in csv.DictReader(f) if r["tmdbId"]})
    ya_reemplazados = json.loads(REEMPLAZOS.read_text()) if REEMPLAZOS.exists() else {}
    pendientes = [i for i in ids if not (DESTINO / f"{i}.json").exists() and str(i) not in ya_reemplazados]
    if args.limite:
        pendientes = pendientes[: args.limite]
    print(f"{len(ids)} tmdbId únicos; {len(pendientes)} por descargar")

    errores: dict[str, str] = {}
    lock = threading.Lock()
    hechos = 0
    inicio = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futuros = [ex.submit(descargar, i, token) for i in pendientes]
        for fut in as_completed(futuros):
            tmdb_id, estado = fut.result()
            with lock:
                hechos += 1
                if estado != "ok":
                    errores[str(tmdb_id)] = estado
                if hechos % 500 == 0:
                    print(f"  {hechos}/{len(pendientes)} ({hechos / (time.time() - inicio):.0f}/s), errores: {len(errores)}", flush=True)

    # Segundo paso: los 404 (IDs eliminados o fusionados) se buscan por su ID de IMDb
    reemplazos = json.loads(REEMPLAZOS.read_text()) if REEMPLAZOS.exists() else {}
    imdb_por_tmdb = {}
    with LINKS.open() as f:
        for r in csv.DictReader(f):
            if r["tmdbId"] and r["imdbId"]:
                imdb_por_tmdb[int(float(r["tmdbId"]))] = f"tt{int(r['imdbId']):07d}"
    previos = json.loads(ERRORES.read_text()) if ERRORES.exists() else {}
    no_encontrados = [int(k) for k, v in {**previos, **errores}.items() if v == "404" and k not in reemplazos]
    for viejo in no_encontrados:
        nuevo = buscar_por_imdb(imdb_por_tmdb.get(viejo), token)
        if nuevo and descargar(nuevo, token)[1] == "ok":
            reemplazos[str(viejo)] = nuevo
    REEMPLAZOS.write_text(json.dumps(reemplazos, indent=1))
    errores = {k: v for k, v in {**previos, **errores}.items() if k not in reemplazos and not (DESTINO / f"{k}.json").exists()}

    ERRORES.write_text(json.dumps(errores, indent=1))
    print(f"Listo en {time.time() - inicio:.0f}s. Recuperados por IMDb: {len(reemplazos)}. "
          f"Errores: {len(errores)} (ver {ERRORES.name})")


if __name__ == "__main__":
    main()
