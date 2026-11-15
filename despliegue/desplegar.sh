#!/usr/bin/env bash
# Despliega PromptCorn con Serverless Framework v4 (pensado para la EC2 de despliegue).
#
#   git pull -> empaqueta el código (con dependencias para Linux) -> serverless deploy -> frontend a S3
#
# Uso:  despliegue/desplegar.sh [todo | backend | frontend | datos]     (por defecto: todo)
#   todo      backend + frontend
#   backend   empaqueta y corre `serverless deploy` (Lambdas, layer, API, tablas, bucket web)
#   frontend  compila con la URL de la API (la toma del stack) y sincroniza el bucket web
#   datos     sube ml/artefactos/ y el catálogo a S3; solo donde están los datos (tu máquina)
#
# Secretos: TMDB_TOKEN y GROQ_API_KEY en el entorno. Si existe ~/.promptcorn.env (fuera del repo), se carga.
# Variables: SIN_PULL=1 no hace git pull; SOLO_EMPAQUETAR=1 arma los zips y no despliega; CAPA=1 rearma la layer.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$RAIZ/dist/aws"
PY=3.14                       # = provider.runtime de serverless.yml
REGION=us-east-1
STACK=promptcorn-prod         # <service>-<stage> de serverless.yml
BUCKET_DATOS=utec-promptcorn-tools-datos

titulo() { printf '\n== %s\n' "$*"; }
falla() { echo "ERROR: $*" >&2; exit 1; }
salida_stack() {
  aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# shellcheck disable=SC1090
[ -f "$HOME/.promptcorn.env" ] && source "$HOME/.promptcorn.env"

asegurar_uv() {
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null && return
  echo "  (instalando uv en ~/.local/bin)"
  python3 -m pip install --user --quiet uv || falla "no se pudo instalar uv"
}

# ---------- empaquetado ----------

empaquetar() {
  titulo "Empaquetando (Python $PY, Linux x86_64) -> dist/aws/"
  asegurar_uv
  mkdir -p "$DIST"
  local tmp; tmp="$(mktemp -d)"

  rm -f "$DIST/recomendar.zip" "$DIST/herramientas.zip" "$DIST/chat.zip"
  (cd "$RAIZ/tools/recomendar" && zip -q "$DIST/recomendar.zip" ./*.py)
  (cd "$RAIZ/tools/herramientas" && zip -q "$DIST/herramientas.zip" ./*.py)

  uv pip install --quiet --target "$tmp/chat" --python-version "$PY" --python-platform x86_64-manylinux_2_28 \
    --only-binary :all: groq requests
  cp "$RAIZ"/chat/{lambda_function,groq_client,conversation_memory,tools_handler,system_prompt}.py "$tmp/chat/"
  (cd "$tmp/chat" && zip -qr "$DIST/chat.zip" . -x '*/__pycache__/*')

  # La layer casi nunca cambia: se reutiliza para no publicar una versión nueva en cada despliegue
  if [ ! -f "$DIST/capa-numpy.zip" ] || [ "${CAPA:-0}" = 1 ]; then
    uv pip install --quiet --target "$tmp/capa/python" --python-version "$PY" \
      --python-platform x86_64-manylinux_2_28 --only-binary :all: "numpy>=2.3,<3"
    rm -f "$DIST/capa-numpy.zip"
    (cd "$tmp/capa" && zip -qr "$DIST/capa-numpy.zip" python -x '*/__pycache__/*' '*/tests/*')
  fi
  rm -rf "$tmp"
  ls -lh "$DIST"/*.zip
}

# ---------- componentes ----------

backend() {
  empaquetar
  [ "${SOLO_EMPAQUETAR:-0}" = 1 ] && return
  ! grep -q "REEMPLAZAR_CON_TU_ORG" "$RAIZ/serverless.yml" || \
    falla "pon el nombre de tu org de serverless.com en 'org:' de serverless.yml (y haz commit)"
  [ -n "${TMDB_TOKEN:-}" ] || falla "falta TMDB_TOKEN en el entorno (ver ~/.promptcorn.env en docs/despliegue.md)"
  [ -n "${GROQ_API_KEY:-}" ] || falla "falta GROQ_API_KEY en el entorno (ver ~/.promptcorn.env en docs/despliegue.md)"
  command -v serverless >/dev/null || falla "falta Serverless Framework: npm install -g serverless@4.46.0"
  titulo "serverless deploy"
  (cd "$RAIZ" && serverless deploy)
}

frontend() {
  command -v npm >/dev/null || falla "falta Node/npm (ver docs/despliegue.md)"
  titulo "Frontend"
  local api bucket sitio
  api=$(salida_stack HttpApiUrl)
  bucket=$(salida_stack BucketWebNombre)
  sitio=$(salida_stack SitioWebUrl)
  [ -n "$api" ] && [ "$api" != "None" ] || falla "no encontré el stack $STACK: despliega primero el backend"
  echo "  API del chat: $api/chat"
  (cd "$RAIZ/frontend" && npm ci --silent && VITE_API_URL="$api/chat" npm run build --silent)
  # Documentación interactiva (Swagger UI en /docs/) con la URL real de la API
  sed "s|__API_URL__|$api|" "$RAIZ/docs/openapi.yaml" > "$RAIZ/frontend/dist/docs/openapi.yaml"
  aws s3 sync "$RAIZ/frontend/dist/" "s3://$bucket/" --delete --only-show-errors --region "$REGION"
  echo "  Sitio: $sitio"
  echo "  Documentación de la API: $sitio/docs/"
}

datos() {
  titulo "Datos -> s3://$BUCKET_DATOS/"
  [ -f "$RAIZ/ml/artefactos/vectores.npy" ] || falla "no hay ml/artefactos/: corre '.venv/bin/python -I ml/entrenar.py' \
(los datos no están en el repo: esto se hace en la máquina que tiene data/)"
  [ -x "$RAIZ/.venv/bin/python" ] || falla "falta .venv (uv sync)"
  "$RAIZ/.venv/bin/python" -I "$RAIZ/scripts/exportar_catalogo.py" --salida "$DIST/catalogo"
  for f in vectores.npy catalogo_ml.json meta.json; do
    aws s3 cp "$RAIZ/ml/artefactos/$f" "s3://$BUCKET_DATOS/modelo/$f" --only-show-errors --region "$REGION"
  done
  for f in catalogo.json ids_externos.json; do
    aws s3 cp "$DIST/catalogo/$f" "s3://$BUCKET_DATOS/catalogo/$f" --only-show-errors --region "$REGION"
  done
  echo "  Listo. Las Lambdas cargan los datos nuevos al reiniciarse (el próximo 'desplegar.sh backend' las reinicia)."
}

# ---------- main ----------

if [ "${SIN_PULL:-0}" != 1 ] && [ "${1:-todo}" != datos ]; then
  titulo "git pull"
  git -C "$RAIZ" pull --ff-only
fi

case "${1:-todo}" in
  todo) backend; [ "${SOLO_EMPAQUETAR:-0}" = 1 ] || frontend ;;
  backend) backend ;;
  frontend) frontend ;;
  datos) datos ;;
  *) falla "uso: despliegue/desplegar.sh [todo | backend | frontend | datos]" ;;
esac

titulo "Listo"
