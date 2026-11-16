"""Pruebas del recomendador y de la Lambda /recomendar (sin AWS).

Uso: .venv/bin/python -I -m unittest discover -s tests -v
Las pruebas con el modelo real se saltan si no existen ml/artefactos/ (correr ml/entrenar.py antes).
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools" / "recomendar"))
import handler  # noqa: E402
from recomendador import Recomendador  # noqa: E402

# Catálogo de juguete: dos "gustos" (eje x = acción, eje y = romance)
VECTORES = np.array([[1, 0], [0.9, 0.1], [0.8, 0.2], [0, 1], [0.1, 0.9], [0.7, 0.7]], dtype=np.float32)
VECTORES /= np.linalg.norm(VECTORES, axis=1, keepdims=True)
CATALOGO = [
    {"id": 1, "titulo": "Acción 1", "anio": 2000, "duracion_min": 120, "generos": ["Acción"], "plataformas": ["Netflix"], "popularidad": 0.5, "calidad": 0.5},
    {"id": 2, "titulo": "Acción 2", "anio": 2010, "duracion_min": 150, "generos": ["Acción"], "plataformas": ["HBO Max"], "popularidad": 0.4, "calidad": 0.5},
    {"id": 3, "titulo": "Acción 3", "anio": 2015, "duracion_min": 90, "generos": ["Acción", "Comedia"], "plataformas": ["Netflix"], "popularidad": 0.3, "calidad": 0.5},
    {"id": 4, "titulo": "Romance 1", "anio": 1995, "duracion_min": 100, "generos": ["Romance"], "plataformas": ["Netflix"], "popularidad": 0.9, "calidad": 0.5},
    {"id": 5, "titulo": "Romance 2", "anio": 2005, "duracion_min": 110, "generos": ["Romance"], "plataformas": [], "popularidad": 1.0, "calidad": 0.5},
    {"id": 6, "titulo": "Mixta", "anio": 2012, "duracion_min": 100, "generos": ["Comedia"], "plataformas": ["Disney+"], "popularidad": 0.2, "calidad": 0.5},
]


class TestRecomendador(unittest.TestCase):
    def setUp(self):
        self.rec = Recomendador(VECTORES, CATALOGO, peso_afinidad=0.8)

    def ids(self, r):
        return [x["id"] for x in r]

    def test_perfil_sigue_el_gusto(self):
        r = self.rec.recomendar({1: 5}, n=2)
        self.assertEqual(self.ids(r), [2, 3])
        self.assertEqual(r[0]["motivo"]["id"], 1)
        self.assertEqual(r[0]["motivo"]["calificacion"], 5)

    def test_nota_baja_resta(self):
        r = self.rec.recomendar({1: 1}, n=1)  # odia la acción -> romance arriba
        self.assertIn(r[0]["id"], (4, 5))

    def test_no_repite_vistas_ni_descartadas_ni_excluidas(self):
        r = self.rec.recomendar({1: 5}, descartadas=[2], excluir=[3], n=10)
        self.assertNotIn(1, self.ids(r))
        self.assertNotIn(2, self.ids(r))
        self.assertNotIn(3, self.ids(r))

    def test_filtros(self):
        self.assertEqual(self.ids(self.rec.recomendar(n=10, generos=["Comedia"])), [3, 6])
        self.assertEqual(set(self.ids(self.rec.recomendar(n=10, plataformas=["Netflix"]))), {1, 3, 4})
        self.assertEqual(self.ids(self.rec.recomendar(n=10, duracion_max=95)), [3])
        self.assertEqual(set(self.ids(self.rec.recomendar(n=10, anio_min=2005, anio_max=2012))), {2, 5, 6})
        self.assertNotIn(5, self.ids(self.rec.recomendar(n=10, solo_disponibles=True)))
        self.assertEqual(self.rec.recomendar(n=10, generos=["Terror"]), [])

    def test_orden_reciente(self):
        r = self.rec.recomendar({1: 5}, n=3, orden="reciente")
        anios = [x["anio"] for x in r]
        self.assertEqual(anios, sorted(anios, reverse=True))
        self.assertEqual(r[0]["id"], 3)  # 2015: la más nueva entre las afines

    def test_arranque_en_frio_por_prior(self):
        r = self.rec.recomendar(n=2)
        self.assertEqual(self.ids(r), [5, 4])  # las más populares
        self.assertIsNone(r[0]["afinidad"])
        self.assertIsNone(r[0]["motivo"])

    def test_parecido_a(self):
        r = self.rec.recomendar(parecido_a=4, n=1)
        self.assertEqual(r[0]["id"], 5)
        self.assertEqual(r[0]["motivo"]["id"], 4)


class AlmacenMemoria:
    def __init__(self, vistas=(), plataformas=(), recomendaciones=()):
        self.vistas, self.plataformas, self.recs = list(vistas), list(plataformas), list(recomendaciones)

    def vistas_de(self, usuario):
        return self.vistas

    def plataformas_de(self, usuario):
        return self.plataformas

    def recomendadas_desde(self, usuario, desde):
        return {r["pelicula_id"] for r in self.recs if r["sk"] >= desde}

    def guardar_recomendaciones(self, usuario, items):
        self.recs += items


class TestHandler(unittest.TestCase):
    AHORA = datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        np.save(d / "vectores.npy", VECTORES)
        (d / "catalogo_ml.json").write_text(json.dumps(CATALOGO))
        (d / "meta.json").write_text(json.dumps({"fecha": "2026-11-13", "k": 2, "prior": "popularidad", "peso_afinidad": 0.8}))
        os.environ["DIR_ARTEFACTOS"] = str(d)
        handler._modelo = None

    @classmethod
    def tearDownClass(cls):
        handler._modelo = None
        os.environ.pop("DIR_ARTEFACTOS", None)
        cls.tmp.cleanup()

    def test_usa_vistas_y_plataformas_del_usuario(self):
        al = AlmacenMemoria(vistas=[{"pelicula_id": 1, "estado": "visto", "calificacion": 5}], plataformas=["Netflix"])
        r = handler.recomendar({"cantidad": 2}, al, self.AHORA)
        self.assertEqual(r["modo"], "perfil")
        self.assertEqual([x["id"] for x in r["recomendaciones"]], [3, 4])  # solo Netflix, sin la 1 (vista)
        self.assertEqual(len(al.recs), 2)  # quedaron guardadas

    def test_no_repite_lo_recomendado_en_el_ultimo_dia(self):
        al = AlmacenMemoria(recomendaciones=[
            {"sk": "2026-11-15T10:00:00Z#4", "pelicula_id": 4},   # hace 10 h -> se excluye
            {"sk": "2026-11-13T10:00:00Z#1", "pelicula_id": 1}])  # hace 2 días -> puede volver
        r = handler.recomendar({"cantidad": 5, "guardar": False}, al, self.AHORA)
        ids = [x["id"] for x in r["recomendaciones"]]
        self.assertNotIn(4, ids)
        self.assertIn(1, ids)
        self.assertNotIn(5, ids)  # sin plataforma en Perú
        self.assertEqual(r["modo"], "arranque_en_frio")
        self.assertTrue(any("plataformas guardadas" in a for a in r["avisos"]))

    def test_repetir_incluye_lo_recomendado_hace_poco(self):
        al = AlmacenMemoria(recomendaciones=[{"sk": "2026-11-15T10:00:00Z#4", "pelicula_id": 4}])
        r = handler.recomendar({"cantidad": 5, "guardar": False, "repetir": True}, al, self.AHORA)
        self.assertIn(4, [x["id"] for x in r["recomendaciones"]])
        with self.assertRaises(handler.ErrorEntrada):
            handler.recomendar({"repetir": "si"}, al, self.AHORA)

    def test_vista_sin_nota_solo_se_excluye(self):
        al = AlmacenMemoria(vistas=[{"pelicula_id": 4, "estado": "visto"}])
        r = handler.recomendar({"cantidad": 5, "guardar": False}, al, self.AHORA)
        self.assertEqual(r["modo"], "arranque_en_frio")
        self.assertNotIn(4, [x["id"] for x in r["recomendaciones"]])

    def test_plataformas_del_request_y_errores(self):
        al = AlmacenMemoria(plataformas=["Netflix"])
        r = handler.recomendar({"plataformas": ["Disney+"], "guardar": False}, al, self.AHORA)
        self.assertEqual([x["id"] for x in r["recomendaciones"]], [6])
        with self.assertRaises(handler.ErrorEntrada) as e:
            handler.recomendar({"generos": ["Acción", "Anime"]}, al, self.AHORA)
        self.assertIn("generos_validos", e.exception.cuerpo)
        for demasiadas in (6, 50):  # el máximo es 5
            with self.assertRaises(handler.ErrorEntrada):
                handler.recomendar({"cantidad": demasiadas}, al, self.AHORA)
        handler.recomendar({"cantidad": 5, "guardar": False}, al, self.AHORA)
        self.assertEqual(handler.recomendar({"cantidad": "2", "guardar": False}, al, self.AHORA)["filtros_aplicados"]["plataformas"], ["Netflix"])

    def test_plataformas_null_usa_las_del_perfil(self):
        al = AlmacenMemoria(plataformas=["Disney+"])
        r = handler.recomendar({"plataformas": None, "anio_min": None, "guardar": False}, al, self.AHORA)
        self.assertEqual(r["filtros_aplicados"]["plataformas"], ["Disney+"])
        self.assertEqual([x["id"] for x in r["recomendaciones"]], [6])

    def test_parecido_fuera_del_modelo_avisa(self):
        r = handler.recomendar({"parecido_a": 999, "guardar": False}, AlmacenMemoria(), self.AHORA)
        self.assertEqual(r["modo"], "arranque_en_frio")
        self.assertTrue(any("parecidas" in a for a in r["avisos"]))

    def test_lambda_handler_api_gateway(self):
        handler._almacen = AlmacenMemoria(plataformas=["Netflix"])
        try:
            r = handler.lambda_handler({"body": json.dumps({"cantidad": 1, "guardar": False})}, None)
            self.assertEqual(r["statusCode"], 200)
            self.assertEqual(len(json.loads(r["body"])["recomendaciones"]), 1)
            r = handler.lambda_handler({"body": "no es json"}, None)
            self.assertEqual(r["statusCode"], 400)
            r = handler.lambda_handler({"cantidad": 0}, None)  # invocación directa
            self.assertEqual(r["status"], 400)
            # por HTTP no se puede elegir otro usuario
            vistos = []
            handler._almacen.vistas_de = lambda u: vistos.append(u) or []
            handler.lambda_handler({"body": json.dumps({"usuario_id": "otro", "guardar": False})}, None)
            handler.lambda_handler({"usuario_id": "otro", "guardar": False}, None)
            self.assertEqual(vistos, [handler.USUARIO, "otro"])
        finally:
            handler._almacen = None


ARTEFACTOS = RAIZ / "ml" / "artefactos"


@unittest.skipUnless((ARTEFACTOS / "vectores.npy").exists(), "falta entrenar (ml/entrenar.py)")
class TestModeloReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        meta = json.loads((ARTEFACTOS / "meta.json").read_text())
        cls.cat = json.loads((ARTEFACTOS / "catalogo_ml.json").read_text())
        cls.rec = Recomendador(np.load(ARTEFACTOS / "vectores.npy"), cls.cat, meta["peso_afinidad"], meta["prior"])

    def id_de(self, titulo):
        return next(p["id"] for p in self.cat if p["titulo"] == titulo)

    def test_secuela_es_lo_mas_parecido(self):
        r = self.rec.recomendar(parecido_a=self.id_de("Toy Story"), n=3)
        self.assertIn("Toy Story 2", [x["titulo"] for x in r])

    def test_perfil_respeta_filtros_y_explica(self):
        notas = {self.id_de("Interestelar"): 5, self.id_de("El Origen"): 4.5}
        r = self.rec.recomendar(notas, n=5, plataformas=["Netflix"], generos=["Ciencia ficción"])
        self.assertEqual(len(r), 5)
        for x in r:
            self.assertIn("Netflix", x["plataformas"])
            self.assertIn("Ciencia ficción", x["generos"])
            self.assertIn(x["motivo"]["titulo"], ("Interestelar", "El Origen"))


if __name__ == "__main__":
    unittest.main()
