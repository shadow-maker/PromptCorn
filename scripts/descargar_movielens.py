"""Descarga MovieLens ml-latest-small en data/raw/movielens/.

Uso: .venv/bin/python -I scripts/descargar_movielens.py
"""
import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
ESPERADOS = {"movies.csv", "ratings.csv", "links.csv", "tags.csv", "README.txt"}
DESTINO = Path(__file__).resolve().parent.parent / "data" / "raw" / "movielens"


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {URL} ...")
    with urllib.request.urlopen(URL, timeout=60) as r:
        contenido = r.read()
    print(f"  {len(contenido) / 1e6:.2f} MB")

    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        for info in z.infolist():
            nombre = Path(info.filename).name
            # Solo archivos esperados; se ignora la estructura de carpetas del zip
            if info.is_dir() or nombre not in ESPERADOS:
                continue
            (DESTINO / nombre).write_bytes(z.read(info))
            print(f"  -> {DESTINO / nombre}")

    faltan = {"movies.csv", "ratings.csv", "links.csv"} - {p.name for p in DESTINO.iterdir()}
    if faltan:
        raise SystemExit(f"Faltan archivos: {faltan}")
    print("Listo.")


if __name__ == "__main__":
    main()
