"""Pruebas de la Lambda de herramientas (sin AWS ni red: catálogo, API externa y DynamoDB simulados).

Uso: .venv/bin/python -I -m unittest discover -s tests -v
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools" / "herramientas"))
import plataformas as plat  # noqa: E402
from tmdb import ErrorExterno  # noqa: E402

# Ambas Lambdas tienen un handler.py: este se carga con otro nombre para no chocar con el de recomendar
_spec = importlib.util.spec_from_file_location("herramientas_handler", RAIZ / "tools" / "herramientas" / "handler.py")
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)

CATALOGO = {
    "fecha_disponibilidad": "2026-11-12",
    "peliculas": [
        {"id": 1, "titulo": "Toy Story", "anio": 1995, "generos": ["Animación"], "plataformas": ["Disney+"],
         "sinopsis": "Juguetes.", "poster": "/ts.jpg"},
        {"id": 8318, "titulo": "Interestelar", "titulo_original": "Interstellar", "anio": 2014,
         "generos": ["Ciencia ficción"], "plataformas": ["Prime Video", "HBO Max"], "sinopsis": "Espacio."},
        {"id": 7332, "titulo": "El Origen", "titulo_original": "Inception", "anio": 2010,
         "generos": ["Acción"], "plataformas": ["HBO Max", "Netflix"]},
    ],
}
IDS_EXTERNOS = {"1": 862, "8318": 157336, "7332": 27205}


class TMDBFalso:
    def __init__(self, caido=False):
        self.caido = caido

    def buscar(self, titulo, anio=None):
        if self.caido:
            raise ErrorExterno("sin red")
        base = {
            "interstellar": [{"ref": 157336, "titulo": "Interestelar", "anio": 2014, "sinopsis": "x", "poster": "/a.jpg"},
                             {"ref": 999001, "titulo": "Interstellar: Detrás de cámaras", "anio": 2015,
                              "sinopsis": "Documental. " * 80, "poster": None}],
            "oppenheimer": [{"ref": 872585, "titulo": "Oppenheimer", "anio": 2023, "sinopsis": "Física.", "poster": "/o.jpg"}],
        }
        return base.get(titulo.lower(), [])

    def proveedores(self, ref):
        if self.caido:
            raise ErrorExterno("sin red")
        return {"flatrate": [{"nombre": "Amazon Prime Video"}, {"nombre": "Max"}],
                "rent": [{"nombre": "Apple TV"}]}


class AlmacenMemoria:
    def __init__(self):
        self.vistas, self.perfil, self.recs = {}, [], []

    def guardar_vista(self, usuario, item):
        self.vistas[item["pelicula_id"]] = {k: v for k, v in item.items() if v is not None}

    def vistas_de(self, usuario):
        return list(self.vistas.values())

    def plataformas_de(self, usuario):
        return list(self.perfil)

    def guardar_plataformas(self, usuario, lista, fecha):
        self.perfil = list(lista)

    def recomendaciones_de(self, usuario, limite):
        return sorted(self.recs, key=lambda r: r["sk"], reverse=True)[:limite]

    def borrar_usuario(self, usuario):
        borrados = {"vistas": len(self.vistas), "recomendaciones": len(self.recs), "perfil": int(bool(self.perfil))}
        self.vistas, self.recs, self.perfil = {}, [], []
        return borrados


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        (d / "catalogo.json").write_text(json.dumps(CATALOGO))
        (d / "ids_externos.json").write_text(json.dumps(IDS_EXTERNOS))
        os.environ["DIR_CATALOGO"] = str(d)
        h._catalogo = None

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("DIR_CATALOGO", None)
        h._catalogo = None
        cls.tmp.cleanup()

    def setUp(self):
        h._almacen = AlmacenMemoria()
        h._tmdb = TMDBFalso()

    def tearDown(self):
        h._almacen = h._tmdb = None

    def llamar(self, herramienta, content_type="application/json", **args):
        """Como lo llama el chat: POST /<herramienta> por API Gateway."""
        r = h.lambda_handler({"rawPath": f"/{herramienta}", "body": json.dumps(args),
                              "headers": {"content-type": content_type},
                              "requestContext": {"http": {"method": "POST"}}}, None)
        return r["statusCode"], json.loads(r["body"])


class TestBuscar(Base):
    def test_traduce_a_nuestro_id(self):
        estado, r = self.llamar("buscar_pelicula", titulo="Interstellar")
        self.assertEqual(estado, 200)
        primero = r["resultados"][0]
        self.assertEqual((primero["id"], primero["titulo"], primero["en_catalogo"]), (8318, "Interestelar", True))
        self.assertNotIn("ref", primero)  # nunca sale la referencia externa

    def test_fuera_del_catalogo(self):
        _, r = self.llamar("buscar_pelicula", titulo="Interstellar")
        fuera = r["resultados"][1]
        self.assertIsNone(fuera["id"])
        self.assertFalse(fuera["en_catalogo"])
        self.assertLessEqual(len(fuera["sinopsis"]), 401)
        _, r = self.llamar("buscar_pelicula", titulo="Oppenheimer")
        self.assertFalse(r["resultados"][0]["en_catalogo"])

    def test_respaldo_local_si_la_api_cae(self):
        h._tmdb = TMDBFalso(caido=True)
        _, r = self.llamar("buscar_pelicula", titulo="inception")  # por título original, sin mayúsculas
        self.assertEqual(r["resultados"][0]["id"], 7332)
        self.assertTrue(r["avisos"])
        _, r = self.llamar("buscar_pelicula", titulo="El origen", anio=1999)
        self.assertEqual(r["resultados"], [])

    def test_tolera_errores_de_tipeo(self):
        _, r = self.llamar("buscar_pelicula", titulo="Intersteller")  # la API externa no encuentra nada
        self.assertEqual(r["resultados"][0]["id"], 8318)

    def test_tipeo_con_resultados_externos_que_no_tenemos(self):
        h._tmdb.buscar = lambda titulo, anio=None: [
            {"ref": 5, "titulo": "Tiny Toy Stories", "anio": 1996, "sinopsis": None, "poster": None}]
        _, r = self.llamar("buscar_pelicula", titulo="toy stori")
        self.assertEqual(r["resultados"][0]["id"], 1)  # el del catálogo primero
        h._tmdb.buscar = lambda titulo, anio=None: [
            {"ref": 6, "titulo": "Oppenheimer", "anio": 2023, "sinopsis": None, "poster": None}]
        _, r = self.llamar("buscar_pelicula", titulo="Oppenheimer")
        self.assertFalse(r["resultados"][0]["en_catalogo"])  # lo pedido existe, pero no lo tenemos

    def test_requiere_titulo(self):
        estado, r = self.llamar("buscar_pelicula")
        self.assertEqual(estado, 400)


class TestDondeVer(Base):
    def test_en_vivo_normalizado_sin_alquiler(self):
        estado, r = self.llamar("ver_donde_ver", id=8318)
        self.assertEqual(estado, 200)
        self.assertEqual(r["plataformas"], ["Prime Video", "HBO Max"])
        self.assertEqual(r["avisos"], [])

    def test_respaldo_snapshot(self):
        h._tmdb = TMDBFalso(caido=True)
        _, r = self.llamar("ver_donde_ver", id="7332")
        self.assertEqual(r["plataformas"], ["HBO Max", "Netflix"])
        self.assertEqual(r["fecha"], "2026-11-12")
        self.assertTrue(r["avisos"])

    def test_id_inexistente(self):
        estado, r = self.llamar("ver_donde_ver", id=424242)
        self.assertEqual(estado, 404)


class TestRegistrarVista(Base):
    def test_registra_con_nota(self):
        estado, r = self.llamar("registrar_vista", id=8318, calificacion=4.7)
        self.assertEqual(estado, 200)
        self.assertEqual((r["estado"], r["calificacion"]), ("visto", 4.5))  # redondeo a medios puntos
        self.assertEqual(h._almacen.vistas[8318]["calificacion"], 4.5)

    def test_no_me_interesa_sin_nota_y_corrige(self):
        self.llamar("registrar_vista", id=1, calificacion=5)
        _, r = self.llamar("registrar_vista", id=1, estado="no_me_interesa", calificacion=5)
        self.assertIsNone(r["calificacion"])
        self.assertEqual(h._almacen.vistas[1]["estado"], "no_me_interesa")
        self.assertNotIn("calificacion", h._almacen.vistas[1])

    def test_validaciones(self):
        self.assertEqual(self.llamar("registrar_vista", id=8318, calificacion=7)[0], 400)
        self.assertEqual(self.llamar("registrar_vista", id=8318, estado="me_encanto")[0], 400)
        self.assertEqual(self.llamar("registrar_vista", id=999)[0], 404)
        self.assertEqual(self.llamar("registrar_vista")[0], 400)

    def test_lo_que_registra_lo_lee_recomendar(self):
        """Contrato entre herramientas: el formato de Vistas es el que espera tools/recomendar."""
        self.llamar("registrar_vista", id=8318, calificacion=5)
        self.llamar("registrar_vista", id=1, estado="no_me_interesa")
        vistas = h._almacen.vistas_de("x")
        notas = {v["pelicula_id"]: v["calificacion"] for v in vistas
                 if v.get("estado") == "visto" and v.get("calificacion") is not None}
        descartadas = [v["pelicula_id"] for v in vistas if v.get("estado") == "no_me_interesa"]
        self.assertEqual((notas, descartadas), ({8318: 5}, [1]))


class TestPlataformas(Base):
    def test_interpreta_variantes(self):
        validas = ["Disney+", "HBO Max", "Netflix", "Prime Video", "Apple TV+"]
        for texto, esperado in [("netflix", "Netflix"), ("Amazon Prime", "Prime Video"), ("HBO", "HBO Max"),
                                ("disney plus", "Disney+"), ("DISNEY+", "Disney+"), ("Max", "HBO Max"),
                                ("Amazon Prime Video", "Prime Video"), ("Cuevana", None)]:
            self.assertEqual(plat.interpretar(texto, validas), esperado, texto)

    def test_reemplazar_agregar_quitar(self):
        _, r = self.llamar("guardar_plataformas", plataformas=["netflix", "hbo", "Cuevana"])
        self.assertEqual((r["plataformas"], r["no_reconocidas"]), (["Netflix", "HBO Max"], ["Cuevana"]))
        _, r = self.llamar("guardar_plataformas", plataformas=["Disney Plus"], accion="agregar")
        self.assertEqual(r["plataformas"], ["Netflix", "HBO Max", "Disney+"])
        _, r = self.llamar("guardar_plataformas", plataformas=["HBO Max"], accion="quitar")
        self.assertEqual(r["plataformas"], ["Netflix", "Disney+"])

    def test_ninguna_reconocida_no_borra(self):
        self.llamar("guardar_plataformas", plataformas=["Netflix"])
        estado, r = self.llamar("guardar_plataformas", plataformas=["Cuevana"])
        self.assertEqual(estado, 400)
        self.assertIn("plataformas_validas", r)
        self.assertEqual(h._almacen.perfil, ["Netflix"])


class TestHistorial(Base):
    def test_recomendaciones_y_vistas(self):
        h._almacen.recs = [
            {"sk": "2026-11-14T10:00:00Z#1", "fecha": "2026-11-14T10:00:00Z", "pelicula_id": 1, "titulo": "Toy Story",
             "anio": 1995, "plataformas": ["Disney+"], "motivo": None},
            {"sk": "2026-11-15T10:00:00Z#7332", "fecha": "2026-11-15T10:00:00Z", "pelicula_id": 7332,
             "titulo": "El Origen", "anio": 2010, "plataformas": ["HBO Max"],
             "motivo": {"id": 8318, "titulo": "Interestelar", "calificacion": 5}}]
        self.llamar("registrar_vista", id=8318, calificacion=5)
        _, r = self.llamar("obtener_historial")
        self.assertEqual([x["id"] for x in r["recomendaciones"]], [7332, 1])  # más reciente primero
        self.assertEqual(r["vistas"][0]["titulo"], "Interestelar")
        _, r = self.llamar("obtener_historial", tipo="vistas", limite=1)
        self.assertNotIn("recomendaciones", r)


class TestReiniciar(Base):
    def test_exige_confirmacion(self):
        self.llamar("registrar_vista", id=8318, calificacion=5)
        estado, r = self.llamar("reiniciar_usuario")
        self.assertEqual(estado, 400)
        self.assertEqual(len(h._almacen.vistas), 1)  # no borró nada

    def test_solo_json(self):
        self.llamar("registrar_vista", id=8318, calificacion=5)
        estado, _ = self.llamar("reiniciar_usuario", content_type="text/plain", confirmar="BORRAR")
        self.assertEqual(estado, 415)
        self.assertEqual(len(h._almacen.vistas), 1)  # no borró nada

    def test_borra_todo(self):
        self.llamar("registrar_vista", id=8318, calificacion=5)
        self.llamar("guardar_plataformas", plataformas=["Netflix"])
        h._almacen.recs = [{"sk": "2026-11-15T10:00:00Z#1", "pelicula_id": 1}]
        estado, r = self.llamar("reiniciar_usuario", confirmar="BORRAR")
        self.assertEqual(estado, 200)
        self.assertEqual(r["borrados"], {"vistas": 1, "recomendaciones": 1, "perfil": 1})
        _, hist = self.llamar("obtener_historial")
        self.assertEqual((hist["vistas"], hist["recomendaciones"]), ([], []))


class TestEntrada(Base):
    def test_ruta_desconocida(self):
        estado, r = self.llamar("borrar_todo")
        self.assertEqual(estado, 404)
        self.assertIn("herramientas", r)

    def test_invocacion_directa(self):
        r = h.lambda_handler({"herramienta": "ver_donde_ver", "id": 1}, None)
        self.assertEqual(r["plataformas"], ["Prime Video", "HBO Max"])
        r = h.lambda_handler({"herramienta": "ver_donde_ver", "id": 5}, None)
        self.assertEqual(r["status"], 404)

    def test_por_http_no_se_elige_usuario(self):
        usados = []
        h._almacen.plataformas_de = lambda u: usados.append(u) or []
        self.llamar("guardar_plataformas", plataformas=["Netflix"], usuario_id="otro")
        self.assertEqual(usados, [h.USUARIO])


if __name__ == "__main__":
    unittest.main()
