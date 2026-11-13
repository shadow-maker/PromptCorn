# 🍿 PromptCorn

**PromptCorn** (prompt + popcorn) es un chatbot conversacional que recomienda películas disponibles en tus plataformas de streaming. Es un workflow agéntico de **Nivel 3** desplegado en **AWS serverless**.

Proyecto Final del curso Cloud Computing, Maestría en Ciencia de Datos e Inteligencia Artificial (UTEC Posgrado).

## Cómo funciona

```
Chat web ─> API Gateway ─> Lambda del chat ─┬─> Groq (LLM con tool calling)
                                            ├─> API de ML /recomendar (similitud SVD + numpy)
                                            ├─> TMDB (búsqueda, detalle, dónde ver)
                                            └─> DynamoDB (memoria, perfil, vistas, historial)
```

- El **LLM** (vía Groq) entiende el mensaje, elige herramientas de una lista cerrada y redacta la respuesta.
- El **modelo de ML** produce el ranking de recomendaciones a partir de las calificaciones de MovieLens.
- La **memoria conversacional** vive en DynamoDB.

## Funcionalidades del MVP
Registro de plataformas · recomendación conversacional · filtro por disponibilidad · dónde verla · más opciones / refinar · excluir vistas · historial · manejo de respuestas ambiguas · registro de vistas con calificación.

## Estructura
```
docs/
  contexto.md   Enunciado, propuesta, diseño, historias de usuario
  datos.md      Fuentes de datos y plan de consolidación
  status.md     Avance y TODOs
scripts/        descarga de datos y consolidación del catálogo
data/           (no versionado) datos descargados y procesados
```

## Estado
Ver [docs/status.md](docs/status.md).

## Créditos y datos
- Calificaciones: [MovieLens](https://grouplens.org/datasets/movielens/). F. Maxwell Harper and Joseph A. Konstan. 2015. *The MovieLens Datasets: History and Context.* ACM TiiS 5, 4: 19:1–19:19. https://doi.org/10.1145/2827872
- Metadatos: este producto usa la API de TMDB pero no está respaldado ni certificado por TMDB.
- Disponibilidad en plataformas: JustWatch (vía TMDB).

Los datos no se incluyen en el repositorio; se regeneran con los scripts (ver [docs/datos.md](docs/datos.md#cómo-regenerarlo)).
