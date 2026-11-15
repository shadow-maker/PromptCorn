import unittest
from unittest.mock import patch, MagicMock

import tools_handler
from tools_handler import ejecutar_herramienta


@patch.object(tools_handler, "MOCK_MODE", True)
class TestToolsHandlerMock(unittest.TestCase):
    """Las simulaciones respetan el formato de docs/contratos.md."""

    def test_recomendar(self):
        resultado = ejecutar_herramienta(
            "recomendar",
            {"generos": ["Ciencia ficción"], "cantidad": 3}
        )
        self.assertTrue(resultado["demo"])
        self.assertEqual(len(resultado["recomendaciones"]), 3)
        primera = resultado["recomendaciones"][0]
        for campo in ("id", "titulo", "anio", "plataformas", "generos", "motivo"):
            self.assertIn(campo, primera)
        self.assertIsInstance(primera["id"], int)
        self.assertEqual(primera["motivo"]["titulo"], "Interestelar")

    def test_recomendar_sin_resultados_avisa(self):
        resultado = ejecutar_herramienta("recomendar", {"generos": ["Western"]})
        self.assertEqual(resultado["recomendaciones"], [])
        self.assertTrue(resultado["avisos"])

    def test_buscar_pelicula(self):
        resultado = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )
        pelicula = resultado["resultados"][0]
        self.assertEqual(pelicula["id"], 8318)
        self.assertEqual(pelicula["titulo"], "Interestelar")
        self.assertTrue(pelicula["en_catalogo"])

    def test_buscar_fuera_del_catalogo(self):
        resultado = ejecutar_herramienta("buscar_pelicula", {"titulo": "Oppenheimer"})
        pelicula = resultado["resultados"][0]
        self.assertFalse(pelicula["en_catalogo"])
        self.assertIsNone(pelicula["id"])

    def test_ver_donde_ver(self):
        resultado = ejecutar_herramienta("ver_donde_ver", {"id": 8318})
        self.assertEqual(resultado["id"], 8318)
        self.assertIn("HBO Max", resultado["plataformas"])

    def test_ver_donde_ver_id_inexistente(self):
        resultado = ejecutar_herramienta("ver_donde_ver", {"id": 999999})
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["status"], 404)

    def test_registrar_vista(self):
        resultado = ejecutar_herramienta(
            "registrar_vista",
            {"id": 8318, "calificacion": 5}
        )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["estado"], "visto")
        self.assertEqual(resultado["calificacion"], 5)

    def test_guardar_plataformas(self):
        resultado = ejecutar_herramienta(
            "guardar_plataformas",
            {"plataformas": ["netflix", "Disney Plus", "Cuevana"]}
        )
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["plataformas"], ["Netflix", "Disney+"])
        self.assertEqual(resultado["no_reconocidas"], ["Cuevana"])

    def test_obtener_historial(self):
        resultado = ejecutar_herramienta("obtener_historial", {})
        self.assertEqual(resultado["recomendaciones"], [])
        self.assertEqual(resultado["vistas"], [])

    def test_herramienta_inexistente(self):
        with self.assertRaises(ValueError):
            ejecutar_herramienta("herramienta_inexistente", {})

    def test_argumentos_invalidos(self):
        with self.assertRaises(ValueError):
            ejecutar_herramienta("recomendar", "texto")

    def test_encadenamiento_busqueda_y_plataformas(self):
        pelicula = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )["resultados"][0]

        plataformas = ejecutar_herramienta(
            "ver_donde_ver",
            {"id": pelicula["id"]}
        )

        self.assertEqual(plataformas["id"], pelicula["id"])

    def test_encadenamiento_busqueda_y_parecidas(self):
        pelicula = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )["resultados"][0]

        resultado = ejecutar_herramienta(
            "recomendar",
            {"parecido_a": pelicula["id"], "excluir": [pelicula["id"]]}
        )

        ids = [r["id"] for r in resultado["recomendaciones"]]
        self.assertNotIn(pelicula["id"], ids)


@patch.object(tools_handler, "MOCK_MODE", False)
class TestToolsHandlerReal(unittest.TestCase):
    """Modo real: URL base única y errores 400/404 devueltos al LLM."""

    @patch.dict("os.environ", {"API_TOOLS_URL": "https://api.ejemplo/"}, clear=True)
    @patch("tools_handler.requests.post")
    def test_url_base_por_herramienta(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"ok": True})
        ejecutar_herramienta("registrar_vista", {"id": 1})
        self.assertEqual(mock_post.call_args.args[0], "https://api.ejemplo/registrar_vista")

    @patch.dict("os.environ", {"API_TOOLS_URL": "https://api.ejemplo",
                               "API_RECOMENDAR_URL": "https://otra/recomendar"}, clear=True)
    @patch("tools_handler.requests.post")
    def test_url_especifica_tiene_prioridad(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        ejecutar_herramienta("recomendar", {})
        self.assertEqual(mock_post.call_args.args[0], "https://otra/recomendar")

    @patch.dict("os.environ", {}, clear=True)
    def test_sin_url_configurada(self):
        with self.assertRaises(ValueError):
            ejecutar_herramienta("recomendar", {})

    @patch.dict("os.environ", {"API_TOOLS_URL": "https://api.ejemplo"}, clear=True)
    @patch("tools_handler.requests.post")
    def test_error_400_vuelve_al_llm(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"error": "Valores no reconocidos en 'generos': ['Anime'].",
                          "generos_validos": ["Acción", "Animación"]})
        resultado = ejecutar_herramienta("recomendar", {"generos": ["Anime"]})
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["status"], 400)
        self.assertIn("generos_validos", resultado)


if __name__ == "__main__":
    unittest.main()
