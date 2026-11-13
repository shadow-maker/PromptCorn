"""Consolida MovieLens + TMDB en un solo catálogo de PromptCorn.

Entradas (data/raw/, generadas por descargar_movielens.py y descargar_tmdb.py)
Salidas (data/processed/):
  peliculas.parquet / .csv      catálogo, 1 fila por película, con ID propio
  calificaciones.parquet / .csv calificaciones de usuarios con los IDs propios
  plataformas.csv               plataformas de streaming en Perú y cuántas películas tienen
  _interno/ids_externos.csv     id propio -> id externo (solo para consultas en vivo; no es parte del dataset)

Uso: .venv/bin/python -I scripts/consolidar.py
"""
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
ML = RAIZ / "data" / "raw" / "movielens"
TMDB = RAIZ / "data" / "raw" / "tmdb"
SALIDA = RAIZ / "data" / "processed"

# Géneros de respaldo (solo si la película no trae géneros en español)
GENEROS_RESPALDO = {
    "Action": "Acción", "Adventure": "Aventura", "Animation": "Animación", "Children": "Familia",
    "Comedy": "Comedia", "Crime": "Crimen", "Documentary": "Documental", "Drama": "Drama",
    "Fantasy": "Fantasía", "Film-Noir": "Crimen", "Horror": "Terror", "Musical": "Música",
    "Mystery": "Misterio", "Romance": "Romance", "Sci-Fi": "Ciencia ficción", "Thriller": "Suspenso",
    "War": "Bélica", "Western": "Western",
}
RENOMBRAR_GENERO = {"Suspense": "Suspenso"}

# Normalización de plataformas
SUFIJOS_CANAL = [" Amazon Channel", " Apple TV Channel", " Roku Premium Channel", " Standard with Ads",
                 " Basic with Ads", " with Ads"]
RENOMBRAR_PLATAFORMA = {
    "VIX": "ViX", "ViX Premium": "ViX", "Max": "HBO Max", "Disney Plus": "Disney+",
    "Paramount Plus": "Paramount+", "Apple TV Plus": "Apple TV+", "Apple TV": "Apple TV+",
    "Amazon Prime Video": "Prime Video", "Claro video": "Claro Video", "MGM Plus": "MGM+",
    "MUBI": "Mubi",
}
EXCLUIR_PLATAFORMA = {"JustWatch TV Beta"}
TIPOS_SUSCRIPCION = ("flatrate", "free", "ads")  # se excluye alquiler y compra


def normalizar_plataforma(nombre: str) -> str | None:
    nombre = nombre.strip()
    if nombre in EXCLUIR_PLATAFORMA:
        return None
    for s in SUFIJOS_CANAL:
        if nombre.lower().endswith(s.lower()):
            nombre = nombre[: -len(s)].strip()
    return RENOMBRAR_PLATAFORMA.get(nombre, nombre)


def texto(v) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else None
    return v or None


def limpiar_sinopsis(v: str | None) -> str | None:
    """Quita notas de procedencia al final, p. ej. '(Tomado de la página imdb)' o '(FILMAFFINITY)'."""
    if not v:
        return None
    v = re.sub(r"\s*\((?:[^()]*\b(?:tomado|fuente|source|imdb|filmaffinity|wikipedia|sinopsis)\b[^()]*)\)\s*$", "", v, flags=re.I)
    return v.strip() or None


def cargar_tmdb(tmdb_id: int) -> dict | None:
    f = TMDB / f"{tmdb_id}.json"
    return json.loads(f.read_text()) if f.exists() else None


def fila_pelicula(d: dict, generos_ml: str, titulo_ml: str) -> dict:
    tr = d.get("traducciones") or {}
    sinopsis = texto(d.get("overview")) or next(
        (texto(tr.get(k, {}).get("overview")) for k in ("es-MX", "es-ES", "en-US") if texto(tr.get(k, {}).get("overview"))), None
    )
    sinopsis = limpiar_sinopsis(sinopsis)
    generos = [RENOMBRAR_GENERO.get(g["name"], g["name"]) for g in d.get("genres") or []]
    if not generos:
        generos = list(dict.fromkeys(GENEROS_RESPALDO[g] for g in generos_ml.split("|") if g in GENEROS_RESPALDO))
    fecha = texto(d.get("release_date"))
    anio = int(fecha[:4]) if fecha else None
    if anio is None:
        m = re.search(r"\((\d{4})\)\s*$", titulo_ml)
        anio = int(m.group(1)) if m else None
    plataformas = []
    for tipo in TIPOS_SUSCRIPCION:
        for p in (d.get("proveedores_pe") or {}).get(tipo, []):
            n = normalizar_plataforma(p["nombre"])
            if n and n not in plataformas:
                plataformas.append(n)
    titulo = texto(d.get("title")) or texto(d.get("original_title"))
    titulo_original = texto(d.get("original_title"))
    return {
        "titulo": titulo,
        "titulo_original": titulo_original if titulo_original != titulo else None,
        "anio": anio,
        "duracion_min": d.get("runtime") or None,
        "generos": generos,
        "sinopsis": sinopsis,
        "director": ", ".join(d.get("directores") or []) or None,
        "reparto": (d.get("reparto") or [])[:3],
        "idioma_original": texto(d.get("original_language")),
        "pais_origen": d.get("origin_country") or [],
        "puntaje": round(d["vote_average"], 1) if d.get("vote_count") else None,
        "votos": d.get("vote_count") or 0,
        "popularidad": round(d.get("popularity") or 0.0, 2),
        "plataformas": plataformas,
        "poster": texto(d.get("poster_path")),  # ruta relativa; la URL base va en la config de la app
        "_adulto": bool(d.get("adult") or d.get("softcore")),
    }


def main() -> None:
    movies = pd.read_csv(ML / "movies.csv")
    links = pd.read_csv(ML / "links.csv")
    ratings = pd.read_csv(ML / "ratings.csv")
    base = movies.merge(links[["movieId", "tmdbId"]], on="movieId", how="left")
    reporte = {"peliculas_origen": len(base), "calificaciones_origen": len(ratings)}

    # 1. Sin vínculo externo -> no hay metadatos
    reporte["descartadas_sin_vinculo"] = int(base.tmdbId.isna().sum())
    base = base.dropna(subset=["tmdbId"]).astype({"tmdbId": int})
    # IDs externos eliminados que se recuperaron con su ID vigente
    reemplazos = {int(k): v for k, v in json.loads((RAIZ / "data" / "raw" / "tmdb_reemplazos.json").read_text()).items()}
    base["tmdbId"] = base.tmdbId.map(lambda i: reemplazos.get(i, i))

    # 2. Unir metadatos
    filas, sin_metadatos = [], 0
    for r in base.itertuples():
        d = cargar_tmdb(r.tmdbId)
        if d is None:
            sin_metadatos += 1
            continue
        filas.append({"movieId": r.movieId, "tmdbId": r.tmdbId, **fila_pelicula(d, r.genres, r.title)})
    reporte["descartadas_sin_metadatos"] = sin_metadatos
    cat = pd.DataFrame(filas)

    # 3. Contenido adulto fuera
    reporte["descartadas_adultas"] = int(cat._adulto.sum())
    cat = cat[~cat._adulto].drop(columns="_adulto")

    # 4. Duplicados: varias entradas que son la misma película -> una sola
    cat = cat.sort_values("movieId")
    reporte["fusionadas_duplicadas"] = int(cat.tmdbId.duplicated().sum())
    remapeo_mid = cat.groupby("tmdbId").movieId.transform("first")  # movieId -> movieId canónico
    mid_canonico = dict(zip(cat.movieId, remapeo_mid))
    cat = cat.drop_duplicates("tmdbId", keep="first").reset_index(drop=True)

    # 5. ID propio correlativo (estable: orden de alta en el catálogo de origen)
    cat.insert(0, "id", range(1, len(cat) + 1))
    id_por_canonico = dict(zip(cat.movieId, cat.id))
    mid_a_id = {mid: id_por_canonico[canon] for mid, canon in mid_canonico.items()}

    # 6. Calificaciones con IDs propios
    cal = ratings[ratings.movieId.isin(mid_a_id)].copy()
    reporte["calificaciones_descartadas"] = len(ratings) - len(cal)
    cal["pelicula_id"] = cal.movieId.map(mid_a_id)
    cal["fecha"] = pd.to_datetime(cal.timestamp, unit="s").dt.date
    cal = (
        cal.groupby(["userId", "pelicula_id"], as_index=False)  # si un usuario calificó ambos duplicados
        .agg(calificacion=("rating", "mean"), fecha=("fecha", "max"))
        .rename(columns={"userId": "usuario_id"})
    )
    cal["calificacion"] = (cal.calificacion * 2).round() / 2  # mantener escala de medias estrellas

    # 7. Salidas
    ids_externos = cat[["id", "tmdbId"]].rename(columns={"tmdbId": "ref_externa"})
    cat = cat.drop(columns=["movieId", "tmdbId"])
    cat = cat.astype({"anio": "Int64", "duracion_min": "Int64", "votos": int})

    (SALIDA / "_interno").mkdir(parents=True, exist_ok=True)
    cat.to_parquet(SALIDA / "peliculas.parquet", index=False)
    cal.to_parquet(SALIDA / "calificaciones.parquet", index=False)
    ids_externos.to_csv(SALIDA / "_interno" / "ids_externos.csv", index=False)

    csv = cat.copy()
    for col in ("generos", "reparto", "pais_origen", "plataformas"):
        csv[col] = csv[col].map(lambda xs: "|".join(xs))
    csv.to_csv(SALIDA / "peliculas.csv", index=False)
    cal.to_csv(SALIDA / "calificaciones.csv", index=False)

    plataformas = cat.plataformas.explode().dropna().value_counts().rename_axis("plataforma").reset_index(name="n_peliculas")
    plataformas.to_csv(SALIDA / "plataformas.csv", index=False)

    reporte.update({
        "peliculas_final": len(cat),
        "calificaciones_final": len(cal),
        "usuarios": int(cal.usuario_id.nunique()),
        "peliculas_con_plataforma_pe": int(cat.plataformas.map(len).gt(0).sum()),
        "sin_sinopsis": int(cat.sinopsis.isna().sum()),
        "sin_duracion": int(cat.duracion_min.isna().sum()),
        "sin_poster": int(cat.poster.isna().sum()),
        "fecha_disponibilidad": date.today().isoformat(),
    })
    (SALIDA / "reporte.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False))
    print(json.dumps(reporte, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
