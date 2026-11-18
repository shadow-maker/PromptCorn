
import json
import os
import time
from groq import Groq


# ==================================================
# 1. CONFIGURACION
# ==================================================

def _leer_api_key():
    """
    La key vive en SSM Parameter Store (SecureString); la variable
    GROQ_API_KEY_PARAM tiene el nombre del parámetro.
    GROQ_API_KEY directo queda para pruebas locales.
    """
    if os.getenv("GROQ_API_KEY"):
        return os.getenv("GROQ_API_KEY")
    parametro = os.getenv("GROQ_API_KEY_PARAM")
    if parametro:
        import boto3
        respuesta = boto3.client("ssm").get_parameter(
            Name=parametro,
            WithDecryption=True
        )
        return respuesta["Parameter"]["Value"]
    return None


# Segunda cuenta de Groq (opcional): GROQ_API_KEY_2. Con dos keys se reparte la
# carga y, si una choca con el límite por minuto, el mensaje sigue con la otra.
API_KEYS = [k for k in (_leer_api_key(), os.getenv("GROQ_API_KEY_2")) if k]

MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

if not API_KEYS:
    raise ValueError(
        "No se encontro la key de Groq. Configura GROQ_API_KEY_PARAM "
        "(parametro de SSM) o GROQ_API_KEY (pruebas locales)."
    )

# "alternar" (por defecto): cada mensaje del usuario va a la cuenta siguiente.
# "respaldo": siempre la primera; la segunda solo cuando la primera llega al límite.
ROTACION = os.getenv("GROQ_ROTACION", "alternar")

# Si una cuenta da 429 y no dice cuánto esperar, se deja descansar este tiempo.
DESCANSO_SEGUNDOS = 60


# ==================================================
# 2. CREAR CLIENTES GROQ (uno por cuenta)
# ==================================================

# La Lambda tiene 29 s (API Gateway corta a los 30): cada llamada a Groq debe
# fallar rápido en vez de esperar reintentos largos por el límite de tokens
# por minuto. lambda_function controla el presupuesto total. Con dos cuentas
# no se reintenta en la misma: un 429 pasa al toque a la otra.
_REINTENTOS = int(os.getenv("GROQ_MAX_RETRIES", "1" if len(API_KEYS) == 1 else "0"))

clientes = [
    Groq(
        api_key=key,
        timeout=float(os.getenv("GROQ_TIMEOUT", "12")),
        max_retries=_REINTENTOS
    )
    for key in API_KEYS
]

# Estado del contenedor de la Lambda (se conserva entre invocaciones "tibias").
_turnos = 0                                   # mensajes atendidos
_cuenta_actual = 0                            # índice en clientes
_descansa_hasta = [0.0] * len(clientes)       # time.time() hasta el que una cuenta está en el límite


def _disponible(i):
    return time.time() >= _descansa_hasta[i]


def nuevo_turno():
    """
    Se llama una vez por mensaje del usuario: elige la cuenta del turno.
    Todas las llamadas a Groq de ese mensaje usan la misma cuenta (salvo que
    llegue al límite). Devuelve el número de cuenta (1 o 2).
    """
    global _turnos, _cuenta_actual
    n = len(clientes)
    preferida = _turnos % n if ROTACION == "alternar" else 0
    _turnos += 1
    for paso in range(n):
        if _disponible((preferida + paso) % n):
            _cuenta_actual = (preferida + paso) % n
            break
    else:
        _cuenta_actual = preferida   # todas en el límite: se intenta igual
    return _cuenta_actual + 1


def _segundos_de_espera(error):
    """Lo que Groq pide esperar (header retry-after); si no viene, DESCANSO_SEGUNDOS."""
    try:
        return max(1.0, float(error.response.headers.get("retry-after")))
    except Exception:
        return float(DESCANSO_SEGUNDOS)


# ==================================================
# 3. FUNCION DE CONSULTA
# ==================================================

def consultar_groq(messages, tools=None):
    """
    Envia una conversacion a Groq.

    messages:
        Historial de mensajes de la conversacion.

    tools:
        Lista de herramientas disponibles para Tool Calling.

    Retorna:
        El mensaje generado por el modelo.
    """

    parametros = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_completion_tokens": 1024
    }

    # gpt-oss razona antes de responder y esos tokens cuentan para el limite
    # por minuto de Groq: con esfuerzo "low" gasta mucho menos.
    if MODEL.startswith("openai/gpt-oss"):
        parametros["extra_body"] = {
            "reasoning_effort": os.getenv("GROQ_REASONING_EFFORT", "low")
        }

    # Incorporar herramientas cuando esten disponibles
    if tools is not None:
        parametros["tools"] = tools
        parametros["tool_choice"] = "auto"

    # Consultar modelo. Si la cuenta del turno llega al límite (429) y hay
    # otra disponible, se cambia a la otra y se repite la misma consulta.
    global _cuenta_actual
    probadas = set()
    while True:
        probadas.add(_cuenta_actual)
        try:
            response = clientes[_cuenta_actual].chat.completions.create(
                **parametros
            )
            break
        except Exception as error:
            if type(error).__name__ != "RateLimitError":
                raise
            _descansa_hasta[_cuenta_actual] = time.time() + _segundos_de_espera(error)
            otras = [i for i in range(len(clientes))
                     if i not in probadas and _disponible(i)]
            if not otras:
                raise
            print(json.dumps({
                "tipo": "groq_cambio_de_cuenta",
                "de": _cuenta_actual + 1,
                "a": otras[0] + 1
            }))
            _cuenta_actual = otras[0]

    # Consumo de tokens en CloudWatch (para vigilar el límite por minuto de Groq)
    uso = getattr(response, "usage", None)
    if uso is not None:
        print(json.dumps({
            "tipo": "groq",
            "modelo": MODEL,
            "cuenta": _cuenta_actual + 1,
            "tokens_entrada": getattr(uso, "prompt_tokens", None),
            "tokens_salida": getattr(uso, "completion_tokens", None)
        }))

    # Devolver el mensaje completo:
    # puede contener texto o solicitudes de herramientas
    return response.choices[0].message
