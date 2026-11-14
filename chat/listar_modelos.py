
import os
from groq import Groq

client = Groq(
    api_key=os.environ["GROQ_API_KEY"]
)

modelos = client.models.list()

print("\nMODELOS DISPONIBLES EN TU CUENTA:\n")

for modelo in modelos.data:
    print(modelo.id)
