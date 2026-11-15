#!/usr/bin/env bash
# Actualiza PromptCorn en AWS desde el repo: git pull -> empaqueta -> sube a Lambda / S3.
# Pensado para AWS CloudShell (ya trae git, python3, node y AWS CLI con las credenciales del lab).
# También sirve en tu máquina si tienes AWS CLI con las credenciales del Learner Lab.
#
# Uso:  despliegue/actualizar.sh [componente ...]
#   (sin argumentos)  recomendar herramientas chat      <- lo normal tras un cambio de código
#   recomendar        código de la Lambda del modelo
#   herramientas      código de la Lambda de las 5 herramientas
#   chat              código de la Lambda del chat (con groq y requests para Linux)
#   frontend          compila con CHAT_API_URL y sincroniza el bucket web
#   capa              publica una versión nueva de la layer de numpy y la conecta a recomendar
#   modelo            sube ml/artefactos/ a S3 (requiere haber entrenado en esta máquina)
#   catalogo          exporta el catálogo y lo sube a S3 (requiere data/processed/ en esta máquina)
#   todo              capa + las 3 Lambdas + frontend (+ modelo y catalogo si hay datos locales)
#
# Variables: DRY_RUN=1 muestra los comandos de AWS sin ejecutarlos; SIN_PULL=1 no hace git pull.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=despliegue/config.sh
source "$RAIZ/despliegue/config.sh"
DIST="$RAIZ/dist/aws"
PY="${RUNTIME#python}"   # 3.14

aws_() { echo "  aws $*"; [ "${DRY_RUN:-0}" = 1 ] || aws --region "$REGION" "$@"; }
titulo() { printf '\n== %s\n' "$*"; }
falla() { echo "ERROR: $*" >&2; exit 1; }

asegurar_uv() {
  command -v uv >/dev/null && return
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null && return
  echo "  (instalando uv en ~/.local/bin)"
  python3 -m pip install --user --quiet uv || falla "no se pudo instalar uv"
}

esperar() { aws_ lambda wait function-updated --function-name "$1"; }

# Sube el zip y fija lo que no es secreto (runtime, handler, memoria, timeout).
# Las variables de entorno no se tocan: tienen los secretos y se cargan en la consola.
actualizar_lambda() {
  local nombre=$1 zip=$2 handler=$3 memoria=$4 timeout=$5
  aws_ lambda update-function-code --function-name "$nombre" --zip-file "fileb://$zip" \
    --query 'CodeSize' --output text
  esperar "$nombre"
  aws_ lambda update-function-configuration --function-name "$nombre" --runtime "$RUNTIME" \
    --handler "$handler" --memory-size "$memoria" --timeout "$timeout" --query 'LastUpdateStatus' --output text
  esperar "$nombre"
}

ya_hecho() {  # cada Lambda se sube una sola vez por corrida (modelo/catalogo también la redespliegan)
  local var="HECHO_$1"
  [ -n "${!var:-}" ] && return 0
  printf -v "$var" 1
  return 1
}

zip_de_carpeta() {  # zip con los .py de una carpeta (sin dependencias)
  local carpeta=$1 zip=$2
  rm -f "$zip"
  (cd "$carpeta" && zip -q "$zip" ./*.py)
}

# ---------- componentes ----------

recomendar() {
  ya_hecho recomendar && return
  titulo "Lambda $LAMBDA_RECOMENDAR"
  zip_de_carpeta "$RAIZ/tools/recomendar" "$DIST/recomendar.zip"
  actualizar_lambda "$LAMBDA_RECOMENDAR" "$DIST/recomendar.zip" handler.lambda_handler 512 15
}

herramientas() {
  ya_hecho herramientas && return
  titulo "Lambda $LAMBDA_HERRAMIENTAS"
  zip_de_carpeta "$RAIZ/tools/herramientas" "$DIST/herramientas.zip"
  actualizar_lambda "$LAMBDA_HERRAMIENTAS" "$DIST/herramientas.zip" handler.lambda_handler 256 15
}

chat() {
  ya_hecho chat && return
  titulo "Lambda $LAMBDA_CHAT"
  asegurar_uv
  local tmp; tmp="$(mktemp -d)"
  uv pip install --quiet --target "$tmp" --python-version "$PY" --python-platform x86_64-manylinux_2_28 \
    --only-binary :all: groq requests
  cp "$RAIZ"/chat/{lambda_function,groq_client,conversation_memory,tools_handler,system_prompt}.py "$tmp/"
  rm -f "$DIST/chat.zip"
  (cd "$tmp" && zip -qr "$DIST/chat.zip" . -x '*/__pycache__/*')
  rm -rf "$tmp"
  actualizar_lambda "$LAMBDA_CHAT" "$DIST/chat.zip" lambda_function.lambda_handler 256 29
}

capa() {
  titulo "Layer $CAPA_NUMPY (numpy para Python $PY)"
  asegurar_uv
  local tmp; tmp="$(mktemp -d)"
  uv pip install --quiet --target "$tmp/python" --python-version "$PY" --python-platform x86_64-manylinux_2_28 \
    --only-binary :all: "numpy>=2.3,<3"
  rm -f "$DIST/capa-numpy.zip"
  (cd "$tmp" && zip -qr "$DIST/capa-numpy.zip" python -x '*/__pycache__/*' '*/tests/*')
  rm -rf "$tmp"
  local arn
  echo "  aws lambda publish-layer-version --layer-name $CAPA_NUMPY --zip-file fileb://$DIST/capa-numpy.zip ..."
  if [ "${DRY_RUN:-0}" = 1 ]; then
    arn="arn:aws:lambda:$REGION:CUENTA:layer:$CAPA_NUMPY:N"
  else
    arn=$(aws --region "$REGION" lambda publish-layer-version --layer-name "$CAPA_NUMPY" \
      --zip-file "fileb://$DIST/capa-numpy.zip" --compatible-runtimes "$RUNTIME" \
      --compatible-architectures x86_64 --query 'LayerVersionArn' --output text)
    echo "  $arn"
  fi
  aws_ lambda update-function-configuration --function-name "$LAMBDA_RECOMENDAR" --layers "$arn" \
    --query 'LastUpdateStatus' --output text
  esperar "$LAMBDA_RECOMENDAR"
}

modelo() {
  titulo "Modelo -> s3://$BUCKET_DATOS/modelo/"
  [ -f "$RAIZ/ml/artefactos/vectores.npy" ] || falla "no hay ml/artefactos/. Los datos no están en el repo (licencia): \
corre esto desde tu máquina después de '.venv/bin/python -I ml/entrenar.py'."
  for f in vectores.npy catalogo_ml.json meta.json; do
    aws_ s3 cp "$RAIZ/ml/artefactos/$f" "s3://$BUCKET_DATOS/modelo/$f" --only-show-errors
  done
  recomendar  # código nuevo = contenedores nuevos = vuelven a cargar el modelo
}

catalogo() {
  titulo "Catálogo -> s3://$BUCKET_DATOS/catalogo/"
  [ -f "$RAIZ/data/processed/peliculas.parquet" ] && [ -x "$RAIZ/.venv/bin/python" ] || falla "no hay data/processed/ \
o .venv. Los datos no están en el repo (licencia): corre esto desde tu máquina."
  "$RAIZ/.venv/bin/python" -I "$RAIZ/scripts/exportar_catalogo.py" --salida "$DIST/catalogo"
  for f in catalogo.json ids_externos.json; do
    aws_ s3 cp "$DIST/catalogo/$f" "s3://$BUCKET_DATOS/catalogo/$f" --only-show-errors
  done
  herramientas  # para que recarguen el catálogo
}

frontend() {
  titulo "Frontend -> s3://$BUCKET_WEB/"
  [ -n "$CHAT_API_URL" ] || falla "falta CHAT_API_URL (Invoke URL de promptcorn-chat-api + /chat) en despliegue/config.sh"
  (cd "$RAIZ/frontend" && npm ci --silent && VITE_API_URL="$CHAT_API_URL" npm run build --silent)
  aws_ s3 sync "$RAIZ/frontend/dist/" "s3://$BUCKET_WEB/" --delete --only-show-errors
}

# ---------- main ----------

command -v aws >/dev/null || [ "${DRY_RUN:-0}" = 1 ] || falla "no está AWS CLI (en CloudShell ya viene instalado)"
mkdir -p "$DIST"

if [ "${SIN_PULL:-0}" != 1 ]; then
  titulo "git pull"
  git -C "$RAIZ" pull --ff-only
fi

componentes=("$@")
[ ${#componentes[@]} -eq 0 ] && componentes=(recomendar herramientas chat)
if [ "${componentes[*]}" = "todo" ]; then
  componentes=(capa)
  [ -f "$RAIZ/ml/artefactos/vectores.npy" ] && componentes+=(modelo)
  [ -f "$RAIZ/data/processed/peliculas.parquet" ] && componentes+=(catalogo)
  componentes+=(recomendar herramientas chat)
  [ -n "$CHAT_API_URL" ] && componentes+=(frontend)
fi

for c in "${componentes[@]}"; do
  case "$c" in
    recomendar|herramientas|chat|frontend|capa|modelo|catalogo) "$c" ;;
    *) falla "componente desconocido: $c (ver el encabezado de este script)" ;;
  esac
done

titulo "Listo: ${componentes[*]}"
