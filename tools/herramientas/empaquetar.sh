#!/usr/bin/env bash
# Arma lo necesario para subir a mano en la consola de AWS:
#   dist/promptcorn-tools-herramientas.zip   código de la Lambda (sin dependencias: solo stdlib + boto3 del runtime)
#   dist/catalogo/catalogo.json, ids_externos.json   catálogo completo para S3 (prefijo catalogo/)
# Uso: tools/herramientas/empaquetar.sh   (desde cualquier carpeta; requiere haber corrido scripts/consolidar.py)
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$RAIZ/dist"
rm -f "$RAIZ/dist/promptcorn-tools-herramientas.zip"
(cd "$RAIZ/tools/herramientas" && zip -q "$RAIZ/dist/promptcorn-tools-herramientas.zip" handler.py catalogo.py tmdb.py plataformas.py)
"$RAIZ/.venv/bin/python" -I "$RAIZ/scripts/exportar_catalogo.py" --salida "$RAIZ/dist/catalogo"
ls -lh "$RAIZ/dist/promptcorn-tools-herramientas.zip" "$RAIZ/dist/catalogo"
