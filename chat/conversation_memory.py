
import os
import boto3
import uuid

from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key


dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(
    os.environ["CONVERSATIONS_TABLE"]
)


def obtener_conversacion(user_id, limite=12):

    response = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=limite
    )

    items = response.get("Items", [])

    items.reverse()

    return [
        {
            "role": item["role"],
            "content": item["content"]
        }
        for item in items
    ]


def guardar_mensaje(user_id, role, content):

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    table.put_item(
        Item={
            "user_id": user_id,
            "message_id": timestamp + "#" + str(uuid.uuid4()),
            "role": role,
            "content": content
        }
    )
