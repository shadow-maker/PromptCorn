
import unittest
from unittest.mock import patch

from tools_handler import ejecutar_herramienta


class TestToolsHandler(unittest.TestCase):

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_recomendar(self):
        resultado = ejecutar_herramienta(
            "recomendar",
            {"genero": "Ciencia ficción", "limite": 3}
        )
        self.assertEqual(resultado["modo"], "demo")
        self.assertEqual(len(resultado["recomendaciones"]), 3)

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_buscar_pelicula(self):
        resultado = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )
        self.assertEqual(resultado["titulo"], "Interstellar")
        self.assertEqual(resultado["año"], 2014)

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_ver_donde_ver(self):
        resultado = ejecutar_herramienta(
            "ver_donde_ver",
            {"id": "123"}
        )
        self.assertEqual(resultado["pelicula_id"], "123")
        self.assertIn("Netflix", resultado["plataformas"])

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_registrar_vista(self):
        resultado = ejecutar_herramienta(
            "registrar_vista",
            {"id": "123"}
        )
        self.assertTrue(resultado["registrado"])

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_guardar_plataformas(self):
        resultado = ejecutar_herramienta(
            "guardar_plataformas",
            {"plataformas": ["Netflix", "Disney+"]}
        )
        self.assertTrue(resultado["guardado"])
        self.assertEqual(
            resultado["plataformas"],
            ["Netflix", "Disney+"]
        )

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_obtener_historial(self):
        resultado = ejecutar_herramienta(
            "obtener_historial",
            {}
        )
        self.assertEqual(resultado["historial"], [])

    def test_herramienta_inexistente(self):
        with self.assertRaises(ValueError):
            ejecutar_herramienta("herramienta_inexistente", {})

    def test_argumentos_invalidos(self):
        with self.assertRaises(ValueError):
            ejecutar_herramienta("recomendar", "texto")

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_encadenamiento_busqueda_y_plataformas(self):
        pelicula = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )

        self.assertEqual(pelicula["id"], "demo_interstellar")

        plataformas = ejecutar_herramienta(
            "ver_donde_ver",
            {"id": pelicula["id"]}
        )

        self.assertEqual(
            plataformas["pelicula_id"],
            pelicula["id"]
        )
        self.assertIn("Netflix", plataformas["plataformas"])

    @patch.dict("os.environ", {"MOCK_MODE": "true"})
    def test_encadenamiento_busqueda_y_registro(self):
        pelicula = ejecutar_herramienta(
            "buscar_pelicula",
            {"titulo": "Interstellar"}
        )

        registro = ejecutar_herramienta(
            "registrar_vista",
            {"id": pelicula["id"]}
        )

        self.assertTrue(registro["registrado"])
        self.assertEqual(
            registro["pelicula_id"],
            pelicula["id"]
        )


if __name__ == "__main__":
    unittest.main()
