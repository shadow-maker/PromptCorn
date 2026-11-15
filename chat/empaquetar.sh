#!/usr/bin/env bash
# Arma el zip de la Lambda del chat para subir a mano en la consola de AWS (x86_64):
#   dist/promptcorn-chat-python3.14.zip   código + dependencias (groq, requests) para Linux
# boto3 no se incluye: ya viene en el runtime de Lambda.
# Requiere uv. Uso: chat/empaquetar.sh   (desde cualquier carpeta)
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$RAIZ/dist"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DIST"

for PY in 3.14; do
  rm -rf "$TMP/pkg" && mkdir -p "$TMP/pkg"
  uv pip install --quiet --target "$TMP/pkg" --python-version "$PY" \
    --python-platform x86_64-manylinux_2_28 --only-binary :all: groq requests
  cp "$RAIZ"/chat/{lambda_function,groq_client,conversation_memory,tools_handler,system_prompt}.py "$TMP/pkg/"
  rm -f "$DIST/promptcorn-chat-python$PY.zip"
  (cd "$TMP/pkg" && zip -qr "$DIST/promptcorn-chat-python$PY.zip" . -x '*/__pycache__/*')
done

ls -lh "$DIST"/promptcorn-chat-*.zip
