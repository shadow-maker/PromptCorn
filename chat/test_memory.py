
import os
import unittest
from unittest.mock import patch
from botocore.exceptions import ClientError

# Configuración de prueba antes de importar conversation_memory
os.environ["CONVERSATIONS_TABLE"] = "TestConversaciones"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"

import conversation_memory


class TestConversationMemory(unittest.TestCase):

    # PRUEBA 1: Obtener historial correctamente
    @patch.object(conversation_memory.table, "query")
    def test_obtener_conversacion(self, mock_query):

        mock_query.return_value = {
            "Items": [
                {
                    "role": "assistant",
                    "content": "Hola, ¿en qué puedo ayudarte?"
                },
                {
                    "role": "user",
                    "content": "Quiero ver una película."
                }
            ]
        }

        historial = conversation_memory.obtener_conversacion(
            "usuario_001",
            limite=12
        )

        # Debe devolver los mensajes en orden cronológico
        self.assertEqual(
            historial,
            [
                {
                    "role": "user",
                    "content": "Quiero ver una película."
                },
                {
                    "role": "assistant",
                    "content": "Hola, ¿en qué puedo ayudarte?"
                }
            ]
        )

        mock_query.assert_called_once()

        parametros = mock_query.call_args.kwargs

        self.assertEqual(parametros["ScanIndexForward"], False)
        self.assertEqual(parametros["Limit"], 12)

    # PRUEBA 2: Obtener historial vacío
    @patch.object(conversation_memory.table, "query")
    def test_historial_vacio(self, mock_query):

        mock_query.return_value = {"Items": []}

        historial = conversation_memory.obtener_conversacion(
            "usuario_001"
        )

        self.assertEqual(historial, [])

    # PRUEBA 3: Validar user_id al consultar
    def test_user_id_invalido(self):

        with self.assertRaises(ValueError):
            conversation_memory.obtener_conversacion("")

    # PRUEBA 4: Validar límite
    def test_limite_invalido(self):

        with self.assertRaises(ValueError):
            conversation_memory.obtener_conversacion(
                "usuario_001",
                limite=0
            )

    # PRUEBA 5: Guardar mensaje correctamente
    @patch.object(conversation_memory.table, "put_item")
    def test_guardar_mensaje(self, mock_put):

        conversation_memory.guardar_mensaje(
            "usuario_001",
            "user",
            "Quiero ver Interstellar."
        )

        mock_put.assert_called_once()

        item = mock_put.call_args.kwargs["Item"]

        self.assertEqual(item["user_id"], "usuario_001")
        self.assertEqual(item["role"], "user")
        self.assertEqual(
            item["content"],
            "Quiero ver Interstellar."
        )

        # Verificar que message_id tenga timestamp y UUID
        self.assertIn("#", item["message_id"])

    # PRUEBA 6: Rechazar un role inválido
    def test_role_invalido(self):

        with self.assertRaises(ValueError):
            conversation_memory.guardar_mensaje(
                "usuario_001",
                "admin",
                "Mensaje de prueba"
            )

    # PRUEBA 7: Rechazar contenido que no sea texto
    def test_content_invalido(self):

        with self.assertRaises(ValueError):
            conversation_memory.guardar_mensaje(
                "usuario_001",
                "user",
                123
            )

    # PRUEBA 8: Manejar error de DynamoDB al consultar
    @patch.object(conversation_memory.table, "query")
    def test_error_consulta_dynamodb(self, mock_query):

        mock_query.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ProvisionedThroughputExceededException",
                    "Message": "Error simulado"
                }
            },
            "Query"
        )

        with self.assertRaises(RuntimeError):
            conversation_memory.obtener_conversacion(
                "usuario_001"
            )

    # PRUEBA 9: Manejar error de DynamoDB al guardar
    @patch.object(conversation_memory.table, "put_item")
    def test_error_guardar_dynamodb(self, mock_put):

        mock_put.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Error simulado"
                }
            },
            "PutItem"
        )

        with self.assertRaises(RuntimeError):
            conversation_memory.guardar_mensaje(
                "usuario_001",
                "user",
                "Mensaje de prueba"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
