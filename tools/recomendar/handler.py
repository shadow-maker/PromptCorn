"""Lambda `promptcorn-tools-recomendar`: API del modelo de ML de PromptCorn.

Flujo: carga el modelo de S3 (una vez por contenedor) -> lee del usuario sus vistas (`Vistas`), sus
plataformas (`Perfil`) y lo recomendado en el último día (`Recomendaciones`) -> filtra y rankea
(recomendador.py) -> guarda lo entregado en `Recomendaciones` -> responde.

Se puede invocar por API Gateway (POST /recomendar, JSON en el body) o directo desde otra Lambda
(el evento es el JSON). Contrato: docs/contratos.md.

Variables de entorno:
  BUCKET_ARTEFACTOS, PREFIJO_ARTEFACTOS (def. "modelo/")  dónde están vectores.npy, catalogo_ml.json, meta.json
  DIR_ARTEFACTOS                                          (solo local) leer los artefactos de una carpeta
  TABLA_VISTAS, TABLA_PERFIL, TABLA_RECOMENDACIONES       nombres de las tablas DynamoDB
  USUARIO_ID (def. "usuario-demo"), HORAS_SIN_REPETIR (def. 24)
"""
from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np

from recomendador import Recomendador

USUARIO = os.environ.get("USUARIO_ID", "usuario-demo")
HORAS_SIN_REPETIR = float(os.environ.get("HORAS_SIN_REPETIR", "24"))
CANTIDAD_DEFECTO, CANTIDAD_MAX = 3, 10


class ErrorEntrada(Exception):
    """Request inválido: se responde 400 con el mensaje y datos para corregirlo."""

    def __init__(self, mensaje: str, **extra):
        super().__init__(mensaje)
        self.cuerpo = {"error": mensaje, **extra}


# ---------- modelo (se carga una vez por contenedor) ----------

_modelo: tuple[Recomendador, dict] | None = None


def cargar_modelo() -> tuple[Recomendador, dict]:
    global _modelo
    if _modelo is None:
        if os.environ.get("DIR_ARTEFACTOS"):
            carpeta = Path(os.environ["DIR_ARTEFACTOS"])
            leer = lambda nombre: (carpeta / nombre).read_bytes()  # noqa: E731
        else:
            import boto3
            s3 = boto3.client("s3")
            bucket, prefijo = os.environ["BUCKET_ARTEFACTOS"], os.environ.get("PREFIJO_ARTEFACTOS", "modelo/")
            leer = lambda nombre: s3.get_object(Bucket=bucket, Key=prefijo + nombre)["Body"].read()  # noqa: E731
        meta = json.loads(leer("meta.json"))
        catalogo = json.loads(leer("catalogo_ml.json"))
        vectores = np.load(io.BytesIO(leer("vectores.npy")))
        _modelo = Recomendador(vectores, catalogo, peso_afinidad=meta["peso_afinidad"], prior=meta["prior"]), meta
    return _modelo


# ---------- almacenamiento (DynamoDB) ----------

def a_dynamo(x):
    """float -> Decimal (DynamoDB no acepta float), recursivo."""
    if isinstance(x, float):
        return Decimal(str(x))
    if isinstance(x, dict):
        return {k: a_dynamo(v) for k, v in x.items()}
    if isinstance(x, list):
        return [a_dynamo(v) for v in x]
    return x


def de_dynamo(x):
    """Decimal -> int o float, recursivo."""
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, dict):
        return {k: de_dynamo(v) for k, v in x.items()}
    if isinstance(x, list):
        return [de_dynamo(v) for v in x]
    return x


class AlmacenDynamo:
    """Vistas (PK usuario_id, SK pelicula_id), Perfil (PK usuario_id), Recomendaciones (PK usuario_id, SK sk)."""

    def __init__(self):
        import boto3
        db = boto3.resource("dynamodb")
        self.vistas = db.Table(os.environ["TABLA_VISTAS"])
        self.perfil = db.Table(os.environ["TABLA_PERFIL"])
        self.recomendaciones = db.Table(os.environ["TABLA_RECOMENDACIONES"])

    @staticmethod
    def _consultar(tabla, condicion) -> list[dict]:
        items, kwargs = [], {"KeyConditionExpression": condicion}
        while True:
            r = tabla.query(**kwargs)
            items += [de_dynamo(i) for i in r["Items"]]
            if "LastEvaluatedKey" not in r:
                return items
            kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def vistas_de(self, usuario: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        return self._consultar(self.vistas, Key("usuario_id").eq(usuario))

    def plataformas_de(self, usuario: str) -> list[str]:
        item = self.perfil.get_item(Key={"usuario_id": usuario}).get("Item") or {}
        return list(item.get("plataformas") or [])

    def recomendadas_desde(self, usuario: str, desde: str) -> set[int]:
        from boto3.dynamodb.conditions import Key
        items = self._consultar(self.recomendaciones, Key("usuario_id").eq(usuario) & Key("sk").gte(desde))
        return {i["pelicula_id"] for i in items}

    def guardar_recomendaciones(self, usuario: str, items: list[dict]) -> None:
        with self.recomendaciones.batch_writer() as w:
            for item in items:
                w.put_item(Item=a_dynamo({"usuario_id": usuario, **item}))


# ---------- lógica ----------

def _entero(body: dict, campo: str, minimo: int, maximo: int) -> int | None:
    v = body.get(campo)
    if v is None:
        return None
    if isinstance(v, str) and v.strip().isdigit():  # el LLM a veces manda números como texto
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not minimo <= v <= maximo:
        raise ErrorEntrada(f"'{campo}' debe ser un entero entre {minimo} y {maximo}.")
    return int(v)


def _lista_de_textos(body: dict, campo: str, validos: list[str]) -> list[str] | None:
    v = body.get(campo)
    if v is None:
        return None
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ErrorEntrada(f"'{campo}' debe ser una lista de textos.")
    desconocidos = [x for x in v if x not in validos]
    if desconocidos:
        raise ErrorEntrada(f"Valores no reconocidos en '{campo}': {desconocidos}.", **{f"{campo}_validos": validos})
    return v


def recomendar(body: dict, almacen, ahora: datetime | None = None) -> dict:
    """Lógica completa del endpoint, sin nada de API Gateway (testeable con un almacén en memoria)."""
    rec, meta = cargar_modelo()
    ahora = ahora or datetime.now(timezone.utc)
    usuario = str(body.get("usuario_id") or USUARIO)

    cantidad = _entero(body, "cantidad", 1, CANTIDAD_MAX) or CANTIDAD_DEFECTO
    filtros = {
        "generos": _lista_de_textos(body, "generos", rec.generos_validos),
        "duracion_max": _entero(body, "duracion_max", 1, 1000),
        "anio_min": _entero(body, "anio_min", 1800, 2100),
        "anio_max": _entero(body, "anio_max", 1800, 2100),
    }
    parecido_a = _entero(body, "parecido_a", 1, 10**9)
    orden = body.get("orden") or "relevancia"
    if orden not in ("relevancia", "reciente"):
        raise ErrorEntrada("'orden' debe ser 'relevancia' o 'reciente'.")
    excluir = body.get("excluir") or []
    if not isinstance(excluir, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in excluir):
        raise ErrorEntrada("'excluir' debe ser una lista de ids (enteros).")

    # Datos del usuario
    vistas = almacen.vistas_de(usuario)
    notas = {v["pelicula_id"]: v["calificacion"] for v in vistas
             if v.get("estado") == "visto" and v.get("calificacion") is not None}
    descartadas = [v["pelicula_id"] for v in vistas if v.get("estado") == "no_me_interesa"]
    vistas_sin_nota = [v["pelicula_id"] for v in vistas if v.get("estado") == "visto" and v.get("calificacion") is None]
    desde = (ahora - timedelta(hours=HORAS_SIN_REPETIR)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recientes = almacen.recomendadas_desde(usuario, desde)

    avisos = []
    if body.get("plataformas") is not None:  # otras plataformas solo para esta consulta ([] = cualquiera; null = las del perfil)
        plataformas = _lista_de_textos(body, "plataformas", rec.plataformas_validas) or []
    else:
        plataformas = [p for p in almacen.plataformas_de(usuario) if p in rec.plataformas_validas]
        if not plataformas:
            avisos.append("El usuario no tiene plataformas guardadas: se recomendó entre todo lo disponible en Perú.")

    # Modo
    if parecido_a is not None and parecido_a not in rec.fila:
        avisos.append("No hay datos suficientes de esa película para buscar parecidas: se recomendó según el perfil.")
        parecido_a = None
    if parecido_a is not None:
        modo = "parecido"
    elif rec.pesos_perfil(notas, descartadas):
        modo = "perfil"
    else:
        modo = "arranque_en_frio"

    resultados = rec.recomendar(
        notas, descartadas=descartadas, excluir=[*vistas_sin_nota, *recientes, *excluir], n=cantidad,
        parecido_a=parecido_a, orden=orden, plataformas=plataformas, solo_disponibles=True, **filtros)
    if not resultados:
        avisos.append("Ninguna película cumple todos los filtros: sugiere al usuario relajar alguno.")
    elif len(resultados) < cantidad:
        avisos.append(f"Solo {len(resultados)} películas cumplen los filtros.")

    if resultados and body.get("guardar", True):
        fecha = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
        almacen.guardar_recomendaciones(usuario, [
            {"sk": f"{fecha}#{r['id']}", "fecha": fecha, "pelicula_id": r["id"], "titulo": r["titulo"],
             "anio": r["anio"], "plataformas": r["plataformas"], "afinidad": r["afinidad"], "modo": modo,
             "motivo": r["motivo"]}
            for r in resultados])

    return {"modo": modo, "recomendaciones": resultados, "avisos": avisos,
            "filtros_aplicados": {**{k: v for k, v in filtros.items() if v is not None}, "plataformas": plataformas},
            "modelo": {"fecha": meta["fecha"], "k": meta["k"]}}


# ---------- entrada de la Lambda ----------

_almacen = None


def lambda_handler(event, context):
    global _almacen
    via_api = isinstance(event, dict) and ("body" in event or "requestContext" in event)
    try:
        if via_api:
            crudo = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                crudo = base64.b64decode(crudo).decode()
            try:
                body = json.loads(crudo)
            except json.JSONDecodeError:
                raise ErrorEntrada("El body no es JSON válido.")
        else:
            body = event or {}
        if not isinstance(body, dict):
            raise ErrorEntrada("El request debe ser un objeto JSON.")
        if via_api:  # por HTTP no hay autenticación: nadie elige el usuario, siempre es USUARIO_ID
            body.pop("usuario_id", None)
        _almacen = _almacen or AlmacenDynamo()
        estado, respuesta = 200, recomendar(body, _almacen)
    except ErrorEntrada as e:
        estado, respuesta = 400, e.cuerpo
    except Exception as e:  # noqa: BLE001  (se registra en CloudWatch y se responde 500 sin detalles internos)
        print(f"ERROR {type(e).__name__}: {e}")
        estado, respuesta = 500, {"error": "Error interno en el recomendador."}

    if not via_api:
        return respuesta if estado == 200 else {**respuesta, "status": estado}
    return {"statusCode": estado, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(respuesta, ensure_ascii=False)}
