#!/usr/bin/env bash
# Arma los zips para subir a mano en la consola de AWS (Lambda x86_64):
#   dist/promptcorn-tools-recomendar.zip   código de la función (handler.py + recomendador.py)
#   dist/capa-numpy-python3.14.zip         layer con numpy para Linux (Python 3.14)
#   dist/modelo/                           artefactos del modelo para subir a S3 (copia de ml/artefactos)
# Requiere uv. Uso: tools/recomendar/empaquetar.sh   (desde cualquier carpeta)
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="$RAIZ/dist"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DIST"

# 1. Código de la función
rm -f "$DIST/promptcorn-tools-recomendar.zip"
(cd "$RAIZ/tools/recomendar" && zip -q "$DIST/promptcorn-tools-recomendar.zip" handler.py recomendador.py)

# 2. Layer de numpy (wheels de Linux x86_64; la estructura python/ es la que espera Lambda)
for PY in 3.14; do
  rm -rf "$TMP/python" && mkdir -p "$TMP/python"
  uv pip install --quiet --target "$TMP/python" --python-version "$PY" \
    --python-platform x86_64-manylinux_2_28 --only-binary :all: "numpy>=2.3,<3"
  rm -f "$DIST/capa-numpy-python$PY.zip"
  (cd "$TMP" && zip -qr "$DIST/capa-numpy-python$PY.zip" python -x '*/__pycache__/*' '*/tests/*')
done

# 3. Artefactos del modelo
if [ -f "$RAIZ/ml/artefactos/vectores.npy" ]; then
  rm -rf "$DIST/modelo" && cp -R "$RAIZ/ml/artefactos" "$DIST/modelo"
else
  echo "AVISO: faltan los artefactos; corre primero: .venv/bin/python -I ml/entrenar.py" >&2
fi

ls -lh "$DIST" "$DIST/modelo" 2>/dev/null
