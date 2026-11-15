"""Lambda `promptcorn-tools-herramientas`: las 5 herramientas de datos del chat en una sola función.

Rutas (API Gateway, POST con JSON en el body; contrato en docs/contratos.md):
  /buscar_pelicula   título -> películas (búsqueda en vivo, traducida a nuestro id; respaldo: catálogo local)
  /ver_donde_ver     id -> plataformas en Perú hoy (en vivo; respaldo: snapshot del catálogo)
  /registrar_vista   id + estado + nota -> tabla Vistas
  /guardar_plataformas  plataformas + acción -> tabla Perfil
  /obtener_historial    -> tablas Recomendaciones y Vistas
Invocación directa (otra Lambda): {"herramienta": "registrar_vista", ...argumentos}.

Variables de entorno:
  BUCKET_CATALOGO, PREFIJO_CATALOGO (def. "catalogo/")   catalogo.json e ids_externos.json en S3
  DIR_CATALOGO                                          (solo local) leerlos de una carpeta
  TMDB_TOKEN_PARAM                                      parámetro SSM (SecureString) con el token de la API externa
  TABLA_VISTAS, TABLA_PERFIL, TABLA_RECOMENDACIONES, USUARIO_ID (def. "usuario-demo")
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import plataformas as plat
from catalogo import Catalogo
from tmdb import ClienteTMDB, ErrorExterno

USUARIO = os.environ.get("USUARIO_ID", "usuario-demo")
MAX_RESULTADOS = 5
MAX_SINOPSIS = 400


class ErrorHerramienta(Exception):
    def __init__(self, estado: int, mensaje: str, **extra):
        super().__init__(mensaje)
        self.estado = estado
        self.cuerpo = {"error": mensaje, **extra}


def error_entrada(mensaje: str, **extra) -> ErrorHerramienta:
    return ErrorHerramienta(400, mensaje, **extra)


# ---------- dependencias (se crean una vez por contenedor; las pruebas las reemplazan) ----------

_catalogo: Catalogo | None = None
_almacen = None
_tmdb: ClienteTMDB | None = None


def catalogo() -> Catalogo:
    global _catalogo
    if _catalogo is None:
        if os.environ.get("DIR_CATALOGO"):
            carpeta = Path(os.environ["DIR_CATALOGO"])
            leer = lambda nombre: (carpeta / nombre).read_bytes()  # noqa: E731
        else:
            import boto3
            s3 = boto3.client("s3")
            bucket, prefijo = os.environ["BUCKET_CATALOGO"], os.environ.get("PREFIJO_CATALOGO", "catalogo/")
            leer = lambda nombre: s3.get_object(Bucket=bucket, Key=prefijo + nombre)["Body"].read()  # noqa: E731
        _catalogo = Catalogo.desde_bytes(leer("catalogo.json"), leer("ids_externos.json"))
    return _catalogo


def almacen():
    global _almacen
    if _almacen is None:
        _almacen = AlmacenDynamo()
    return _almacen


def tmdb() -> ClienteTMDB:
    global _tmdb
    if _tmdb is None:
        _tmdb = ClienteTMDB()
    return _tmdb


# ---------- DynamoDB ----------

def a_dynamo(x):
    if isinstance(x, float):
        return Decimal(str(x))
    if isinstance(x, dict):
        return {k: a_dynamo(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [a_dynamo(v) for v in x]
    return x


def de_dynamo(x):
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, dict):
        return {k: de_dynamo(v) for k, v in x.items()}
    if isinstance(x, list):
        return [de_dynamo(v) for v in x]
    return x


class AlmacenDynamo:
    def __init__(self):
        import boto3
        db = boto3.resource("dynamodb")
        self.vistas = db.Table(os.environ["TABLA_VISTAS"])
        self.perfil = db.Table(os.environ["TABLA_PERFIL"])
        self.recomendaciones = db.Table(os.environ["TABLA_RECOMENDACIONES"])

    def guardar_vista(self, usuario: str, item: dict) -> None:
        self.vistas.put_item(Item=a_dynamo({"usuario_id": usuario, **item}))

    def vistas_de(self, usuario: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        items, kwargs = [], {"KeyConditionExpression": Key("usuario_id").eq(usuario)}
        while True:
            r = self.vistas.query(**kwargs)
            items += [de_dynamo(i) for i in r["Items"]]
            if "LastEvaluatedKey" not in r:
                return items
            kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def plataformas_de(self, usuario: str) -> list[str]:
        item = self.perfil.get_item(Key={"usuario_id": usuario}).get("Item") or {}
        return list(item.get("plataformas") or [])

    def guardar_plataformas(self, usuario: str, lista: list[str], fecha: str) -> None:
        self.perfil.put_item(Item={"usuario_id": usuario, "plataformas": lista, "actualizado": fecha})

    def recomendaciones_de(self, usuario: str, limite: int) -> list[dict]:
        from boto3.dynamodb.conditions import Key
        r = self.recomendaciones.query(KeyConditionExpression=Key("usuario_id").eq(usuario),
                                       ScanIndexForward=False, Limit=limite)  # SK empieza por la fecha
        return [de_dynamo(i) for i in r["Items"]]

    def borrar_usuario(self, usuario: str) -> dict:
        """Borra todo lo del usuario en las 3 tablas. Devuelve cuántos ítems se borraron en cada una."""
        from boto3.dynamodb.conditions import Key
        borrados = {}
        for nombre, tabla, sk in (("vistas", self.vistas, "pelicula_id"),
                                  ("recomendaciones", self.recomendaciones, "sk")):
            claves, kwargs = [], {"KeyConditionExpression": Key("usuario_id").eq(usuario),
                                  "ProjectionExpression": "usuario_id, #sk",
                                  "ExpressionAttributeNames": {"#sk": sk}}
            while True:
                r = tabla.query(**kwargs)
                claves += r["Items"]
                if "LastEvaluatedKey" not in r:
                    break
                kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
            with tabla.batch_writer() as w:
                for clave in claves:
                    w.delete_item(Key=clave)
            borrados[nombre] = len(claves)
        tenia_perfil = "Item" in self.perfil.get_item(Key={"usuario_id": usuario})
        self.perfil.delete_item(Key={"usuario_id": usuario})
        borrados["perfil"] = int(tenia_perfil)
        return borrados


# ---------- validación ----------

def _entero(body: dict, campo: str, minimo: int, maximo: int, obligatorio: bool = False) -> int | None:
    v = body.get(campo)
    if v is None:
        if obligatorio:
            raise error_entrada(f"Falta '{campo}'.")
        return None
    if isinstance(v, str) and v.strip().isdigit():  # el LLM a veces manda números como texto
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not minimo <= v <= maximo:
        raise error_entrada(f"'{campo}' debe ser un entero entre {minimo} y {maximo}.")
    return int(v)


def _opcion(body: dict, campo: str, opciones: tuple[str, ...]) -> str:
    v = body.get(campo) or opciones[0]
    if v not in opciones:
        raise error_entrada(f"'{campo}' debe ser uno de {list(opciones)}.")
    return v


def _pelicula(body: dict) -> dict:
    pid = _entero(body, "id", 1, 10**9, obligatorio=True)
    p = catalogo().get(pid)
    if p is None:
        raise ErrorHerramienta(404, f"No existe una película con id {pid}. Búscala con buscar_pelicula.")
    return p


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _usuario(body: dict) -> str:
    return str(body.get("usuario_id") or USUARIO)


def _corto(texto: str | None) -> str | None:
    if not texto:
        return None
    return texto if len(texto) <= MAX_SINOPSIS else texto[:MAX_SINOPSIS].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _ficha(p: dict) -> dict:
    return {"id": p["id"], "titulo": p["titulo"], "anio": p.get("anio"), "sinopsis": p.get("sinopsis"),
            "poster": p.get("poster"), "en_catalogo": True}


# ---------- herramientas ----------

def buscar_pelicula(body: dict) -> dict:
    titulo = body.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        raise error_entrada("Falta 'titulo' (texto).")
    anio = _entero(body, "anio", 1800, 2100)
    cat, avisos = catalogo(), []
    try:
        externos = tmdb().buscar(titulo.strip(), anio)
    except ErrorExterno:
        externos = None
        avisos.append("La búsqueda en vivo no respondió: se buscó solo en el catálogo de PromptCorn.")

    resultados, vistos = [], set()
    for r in externos or []:
        pid = cat.id_por_ref.get(r["ref"])
        if pid in vistos:
            continue
        if pid is not None:
            vistos.add(pid)
            resultados.append(_ficha(cat.get(pid)))
        else:
            resultados.append({"id": None, "titulo": r["titulo"], "anio": r["anio"], "sinopsis": _corto(r["sinopsis"]),
                               "poster": r["poster"], "en_catalogo": False})
        if len(resultados) == MAX_RESULTADOS:
            break
    if not any(r["en_catalogo"] for r in resultados):
        # Nada del catálogo (API caída, errores de tipeo como "toy stori", o una película que no tenemos):
        # se busca también en el catálogo local.
        locales = [_ficha(p) for p in cat.buscar_local(titulo, anio, MAX_RESULTADOS)]
        if resultados and _parecido(titulo, resultados[0]["titulo"]) >= 0.8:
            resultados = resultados + locales  # el primero externo es justo lo que pidió (p. ej. un estreno)
        else:
            resultados = locales + resultados
    return {"resultados": resultados[:MAX_RESULTADOS], "avisos": avisos}


def _parecido(a: str, b: str) -> float:
    import difflib
    from catalogo import _clave
    return difflib.SequenceMatcher(None, _clave(a), _clave(b)).ratio()


def ver_donde_ver(body: dict) -> dict:
    p = _pelicula(body)
    cat = catalogo()
    try:
        plataformas = plat.de_proveedores(tmdb().proveedores(cat.ref_por_id[p["id"]]))
        fecha, avisos = datetime.now(timezone.utc).date().isoformat(), []
    except (ErrorExterno, KeyError):
        plataformas, fecha = p["plataformas"], cat.fecha_disponibilidad
        avisos = [f"No se pudo consultar la disponibilidad actual: es la del {fecha}."]
    return {"id": p["id"], "titulo": p["titulo"], "plataformas": plataformas, "fecha": fecha, "avisos": avisos}


def registrar_vista(body: dict) -> dict:
    p = _pelicula(body)
    estado = _opcion(body, "estado", ("visto", "no_me_interesa"))
    nota = body.get("calificacion")
    if isinstance(nota, str):
        try:
            nota = float(nota.replace(",", "."))
        except ValueError:
            raise error_entrada("'calificacion' debe ser un número de 0.5 a 5.")
    if nota is not None:
        if isinstance(nota, bool) or not isinstance(nota, (int, float)) or not 0.5 <= nota <= 5:
            raise error_entrada("'calificacion' debe ser un número de 0.5 a 5.")
        nota = round(nota * 2) / 2  # escala de medios puntos, como los datos del modelo
        nota = int(nota) if nota == int(nota) else nota
    if estado == "no_me_interesa":
        nota = None
    almacen().guardar_vista(_usuario(body), {"pelicula_id": p["id"], "estado": estado, "calificacion": nota,
                                             "fecha": _ahora(), "titulo": p["titulo"]})
    return {"ok": True, "id": p["id"], "titulo": p["titulo"], "estado": estado, "calificacion": nota}


def guardar_plataformas(body: dict) -> dict:
    pedidas = body.get("plataformas")
    if isinstance(pedidas, str):
        pedidas = [pedidas]
    if not isinstance(pedidas, list) or not all(isinstance(x, str) for x in pedidas):
        raise error_entrada("'plataformas' debe ser una lista de textos.")
    accion = _opcion(body, "accion", ("reemplazar", "agregar", "quitar"))
    validas = catalogo().plataformas
    reconocidas, no_reconocidas = [], []
    for texto in pedidas:
        canon = plat.interpretar(texto, validas)
        if canon is None:
            no_reconocidas.append(texto)
        elif canon not in reconocidas:
            reconocidas.append(canon)
    if pedidas and not reconocidas:
        raise error_entrada(f"No se reconoció ninguna plataforma: {no_reconocidas}.", plataformas_validas=validas)

    usuario = _usuario(body)
    actuales = almacen().plataformas_de(usuario)
    if accion == "reemplazar":
        final = reconocidas
    elif accion == "agregar":
        final = actuales + [p for p in reconocidas if p not in actuales]
    else:
        final = [p for p in actuales if p not in reconocidas]
    almacen().guardar_plataformas(usuario, final, _ahora())
    return {"ok": True, "plataformas": final, "no_reconocidas": no_reconocidas}


def obtener_historial(body: dict) -> dict:
    tipo = _opcion(body, "tipo", ("todo", "recomendaciones", "vistas"))
    limite = _entero(body, "limite", 1, 50) or 10
    usuario, cat, salida = _usuario(body), catalogo(), {}
    if tipo in ("todo", "recomendaciones"):
        salida["recomendaciones"] = [
            {"fecha": r.get("fecha"), "id": r["pelicula_id"], "titulo": r.get("titulo"), "anio": r.get("anio"),
             "plataformas": r.get("plataformas") or [], "motivo": r.get("motivo")}
            for r in almacen().recomendaciones_de(usuario, limite)]
    if tipo in ("todo", "vistas"):
        vistas = sorted(almacen().vistas_de(usuario), key=lambda v: v.get("fecha") or "", reverse=True)[:limite]
        salida["vistas"] = [
            {"fecha": v.get("fecha"), "id": v["pelicula_id"],
             "titulo": v.get("titulo") or (cat.get(v["pelicula_id"]) or {}).get("titulo"),
             "estado": v.get("estado"), "calificacion": v.get("calificacion")}
            for v in vistas]
    return salida


def reiniciar_usuario(body: dict) -> dict:
    """Borra vistas, notas, plataformas y recomendaciones del usuario (vuelve al arranque en frío).
    No es una herramienta del chat (el LLM no la conoce): la usa el botón "Reiniciar perfil" del frontend.
    Exige {"confirmar": "BORRAR"} para que no se ejecute por accidente."""
    if body.get("confirmar") != "BORRAR":
        raise error_entrada('Acción destructiva: envía {"confirmar": "BORRAR"} para confirmar.')
    return {"ok": True, "borrados": almacen().borrar_usuario(_usuario(body))}


HERRAMIENTAS = {f.__name__: f for f in (buscar_pelicula, ver_donde_ver, registrar_vista, guardar_plataformas,
                                        obtener_historial, reiniciar_usuario)}


# ---------- entrada de la Lambda ----------

def _ruta(event: dict) -> str | None:
    ruta = event.get("rawPath") or event.get("path") or (event.get("routeKey") or "").split(" ")[-1]
    return ruta.rstrip("/").rsplit("/", 1)[-1] if ruta else None


def lambda_handler(event, context):
    via_api = isinstance(event, dict) and ("body" in event or "requestContext" in event)
    try:
        if not isinstance(event, dict):
            raise error_entrada("El request debe ser un objeto JSON.")
        if via_api:
            nombre = _ruta(event)
            crudo = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                crudo = base64.b64decode(crudo).decode()
            try:
                body = json.loads(crudo)
            except json.JSONDecodeError:
                raise error_entrada("El body no es JSON válido.")
            if not isinstance(body, dict):
                raise error_entrada("El body debe ser un objeto JSON.")
            body.pop("usuario_id", None)  # por HTTP no hay autenticación: siempre el usuario fijo
        else:
            body = dict(event)
            nombre = body.pop("herramienta", None)
        if via_api and nombre == "reiniciar_usuario":
            # Acción destructiva: solo JSON. Un formulario HTML de otro sitio no puede mandar este Content-Type
            # sin pasar por CORS (que solo admite el sitio de PromptCorn).
            tipo = {k.lower(): v for k, v in (event.get("headers") or {}).items()}.get("content-type", "")
            if not tipo.lower().startswith("application/json"):
                raise ErrorHerramienta(415, "reiniciar_usuario solo acepta Content-Type: application/json.")
        if nombre not in HERRAMIENTAS:
            raise ErrorHerramienta(404, f"Herramienta no reconocida: {nombre}.", herramientas=list(HERRAMIENTAS))
        estado, respuesta = 200, HERRAMIENTAS[nombre](body)
    except ErrorHerramienta as e:
        estado, respuesta = e.estado, e.cuerpo
    except Exception as e:  # noqa: BLE001  (detalle en CloudWatch; al cliente, mensaje genérico)
        print(f"ERROR {type(e).__name__}: {e}")
        estado, respuesta = 500, {"error": "Error interno en las herramientas."}

    if not via_api:
        return respuesta if estado == 200 else {**respuesta, "status": estado}
    return {"statusCode": estado, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(respuesta, ensure_ascii=False)}
