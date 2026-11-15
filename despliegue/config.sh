# Configuración del despliegue en AWS (Learner Lab). Sin secretos: el token y la key de Groq
# van en las variables de entorno de cada Lambda, cargadas a mano en la consola.
# Cualquier valor se puede sobrescribir con una variable de entorno al correr el script.

: "${REGION:=us-east-1}"
: "${RUNTIME:=python3.14}"                         # el de las 3 Lambdas (la layer y los binarios son para esta versión)

: "${BUCKET_DATOS:=utec-promptcorn-tools-datos}"   # modelo/ y catalogo/
: "${BUCKET_WEB:=utec-promptcorn-chat-web}"        # frontend (sitio estático)

: "${LAMBDA_RECOMENDAR:=promptcorn-tools-recomendar}"
: "${LAMBDA_HERRAMIENTAS:=promptcorn-tools-herramientas}"
: "${LAMBDA_CHAT:=promptcorn-chat}"
: "${CAPA_NUMPY:=promptcorn-tools-numpy}"

# Invoke URL de promptcorn-chat-api + "/chat". Se compila dentro del frontend (es pública: no es secreto).
: "${CHAT_API_URL:=}"
