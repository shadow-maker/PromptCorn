
import os
import uuid
import boto3

from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


# ==================================================
# 1. CONFIGURACION DE DYNAMODB
# ==================================================

TABLE_NAME = os.getenv("CONVERSATIONS_TABLE")

if not TABLE_NAME:
    raise ValueError(
        "Falta configurar la variable CONVERSATIONS_TABLE."
    )

dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(TABLE_NAME)


# ==================================================
# 2. OBTENER HISTORIAL DE CONVERSACION
# ==================================================

def obtener_conversacion(usuario_id, limite=12):

    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValueError("El usuario_id no es valido.")

    if not isinstance(limite, int) or limite < 1:
        raise ValueError("El limite debe ser un entero positivo.")

    try:

        response = table.query(
            KeyConditionExpression=Key("usuario_id").eq(usuario_id),
            ScanIndexForward=False,
            Limit=limite
        )

        items = response.get("Items", [])

        # Ordenar cronologicamente:
        # del mensaje mas antiguo al mas reciente.
        items.reverse()

        historial = [
            {
                "role": item["rol"],
                "content": item["contenido"]
            }
            for item in items
        ]

        return historial

    except ClientError as error:

        raise RuntimeError(
            f"Error al consultar el historial en DynamoDB: "
            f"{error.response['Error']['Code']}"
        )


# ==================================================
# 3. GUARDAR MENSAJE EN DYNAMODB
# ==================================================

def guardar_mensaje(usuario_id, role, content):

    if not isinstance(usuario_id, str) or not usuario_id.strip():
        raise ValueError("El usuario_id no es valido.")

    if role not in ["user", "assistant"]:
        raise ValueError("El role debe ser user o assistant.")

    if not isinstance(content, str):
        raise ValueError("El contenido debe ser texto.")

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    mensaje_id = (
        timestamp + "#" + str(uuid.uuid4())
    )

    try:

        table.put_item(
            Item={
                "usuario_id": usuario_id,
                "mensaje_id": mensaje_id,
                "rol": role,
                "contenido": content
            }
        )

    except ClientError as error:

        raise RuntimeError(
            f"Error al guardar el mensaje en DynamoDB: "
            f"{error.response['Error']['Code']}"
        )
