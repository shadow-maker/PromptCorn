"""Exporta el catálogo completo para la Lambda de herramientas (va a S3, no al repo).

Salidas (en --salida, por defecto dist/catalogo/):
  catalogo.json      {"fecha_disponibilidad": ..., "peliculas": [...]}, 1 entrada por película (9,649)
  ids_externos.json  {id propio: ref externa}. Interno: solo para las consultas en vivo de las herramientas

Uso: .venv/bin/python -I scripts/exportar_catalogo.py [--salida dist/catalogo]
"""
import argparse
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data" / "processed"
MAX_SINOPSIS = 400


def resumir(texto) -> str | None:
    if not isinstance(texto, str) or not texto:
        return None
    return texto if len(texto) <= MAX_SINOPSIS else texto[:MAX_SINOPSIS].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def valor(v):
    """NaN/NA -> None; arrays -> listas; numpy -> tipos nativos."""
    if hasattr(v, "tolist"):
        return v.tolist()
    if v is None or (isinstance(v, float) and v != v) or v is pd.NA:
        return None
    return v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(RAIZ / "dist" / "catalogo"))
    args = ap.parse_args()
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)

    pel = pd.read_parquet(DATOS / "peliculas.parquet")
    reporte = json.loads((DATOS / "reporte.json").read_text())
    campos = ["id", "titulo", "titulo_original", "anio", "duracion_min", "generos", "sinopsis", "director",
              "reparto", "plataformas", "poster"]
    peliculas = []
    for r in pel[campos].itertuples(index=False):
        p = {c: valor(getattr(r, c)) for c in campos}
        p["sinopsis"] = resumir(p["sinopsis"])
        peliculas.append({k: v for k, v in p.items() if v not in (None, [])} | {"plataformas": p["plataformas"] or []})
    (salida / "catalogo.json").write_text(json.dumps(
        {"fecha_disponibilidad": reporte["fecha_disponibilidad"], "peliculas": peliculas},
        ensure_ascii=False, separators=(",", ":")))

    ids = pd.read_csv(DATOS / "_interno" / "ids_externos.csv")
    (salida / "ids_externos.json").write_text(json.dumps({int(i): int(r) for i, r in zip(ids.id, ids.ref_externa)}))
    tam = sum(f.stat().st_size for f in salida.iterdir()) / 1e6
    print(f"{len(peliculas)} películas -> {salida} ({tam:.1f} MB)")


if __name__ == "__main__":
    main()
