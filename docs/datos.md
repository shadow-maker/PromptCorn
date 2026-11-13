# Datos: catálogo de PromptCorn

El catálogo de PromptCorn es **un solo dataset** con ID propio, generado por scripts a partir de dos fuentes públicas (MovieLens y TMDB). Ni los datos crudos ni los procesados se suben al repo: se regeneran con los scripts.

## Cómo regenerarlo

```bash
uv sync                                                # entorno (.venv) con pandas y pyarrow
.venv/bin/python -I scripts/descargar_movielens.py     # ~1 MB, segundos
.venv/bin/python -I scripts/descargar_tmdb.py          # ~9.7k llamadas, ~6 min; retoma si se corta
.venv/bin/python -I scripts/consolidar.py              # segundos
```

El token de TMDB se lee de la variable `TMDB_TOKEN` o de `~/.config/promptcorn/tmdb_token` (nunca del repo).

## Resultado (`data/processed/`)

| Archivo | Contenido | Filas |
|---|---|---|
| `peliculas.parquet` / `.csv` | Catálogo, 1 fila por película | 9,649 |
| `calificaciones.parquet` / `.csv` | Calificaciones de usuarios (entrada del modelo de ML) | 100,612 (610 usuarios) |
| `plataformas.csv` | Plataformas de streaming en Perú y cuántas películas tiene cada una | 34 |
| `reporte.json` | Conteos de la limpieza y fecha del snapshot de disponibilidad | — |
| `_interno/ids_externos.csv` | `id` → `ref_externa` | 9,649 |

En el CSV, las columnas de lista van separadas por `|`. En Parquet son listas reales.

### `peliculas`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | int | ID propio de PromptCorn (1..N) |
| `titulo` | str | Título en español latino |
| `titulo_original` | str / null | Título original, solo si difiere de `titulo` |
| `anio` | int | Año de estreno |
| `duracion_min` | int | Duración en minutos |
| `generos` | list[str] | Géneros en español (ver lista abajo) |
| `sinopsis` | str | Sinopsis en español (respaldo: inglés) |
| `director` | str | Director(es), separados por coma |
| `reparto` | list[str] | 3 actores principales |
| `idioma_original` | str | Código ISO 639-1 (`en`, `es`, `fr`…) |
| `pais_origen` | list[str] | Códigos ISO 3166-1 (`US`, `GB`…) |
| `puntaje` | float | Puntaje promedio 0–10 |
| `votos` | int | Cantidad de votos detrás del puntaje |
| `popularidad` | float | Índice de popularidad actual (sirve para desempatar) |
| `plataformas` | list[str] | Plataformas en Perú donde se puede ver con suscripción o gratis (snapshot) |
| `poster` | str | Ruta relativa del póster; la URL base va en la config de la app |

Géneros: Drama, Comedia, Suspenso, Romance, Acción, Crimen, Aventura, Ciencia ficción, Terror, Familia, Fantasía, Misterio, Animación, Historia, Documental, Música, Bélica, Película de TV, Western.

Plataformas principales (n.º de películas): Disney+ 838, Prime Video 776, HBO Max 648, Mercado Play 446, Netflix 376, Plex 281, Universal+ 277, Sony One 215, MGM+ 205, Pluto TV 113, Claro Video 109, Mubi 96, Paramount+ 94… 3,589 películas (37 %) tienen al menos una plataforma en Perú.

### `calificaciones`

| Columna | Tipo | Descripción |
|---|---|---|
| `usuario_id` | int | Usuario anónimo (1..610) |
| `pelicula_id` | int | `peliculas.id` |
| `calificacion` | float | 0.5 a 5.0 en medias estrellas |
| `fecha` | date | Fecha de la calificación (útil para separar train/test por tiempo) |

### `_interno/ids_externos.csv`

No forma parte del dataset. Solo existe porque dos herramientas consultan en vivo: `buscar_pelicula` (texto → película) y `ver_donde_ver` (disponibilidad actual). La búsqueda devuelve una referencia externa que hay que traducir a nuestro `id`, y viceversa.

## Limpieza aplicada

| Paso | Efecto |
|---|---|
| Películas sin vínculo entre fuentes | −8 |
| Sin metadatos (miniseries de TV o fichas eliminadas; 31 se recuperaron por ID de IMDb) | −82 |
| Contenido adulto | −2 |
| Duplicados (la misma película con dos IDs) fusionados, junto con sus calificaciones | −1 |
| Calificaciones de películas descartadas | −223 |
| Géneros: un solo vocabulario en español (respaldo con los géneros originales si faltan); se descarta "IMAX" | — |
| Plataformas: canales unificados ("Universal+ Amazon Channel" → "Universal+"), variantes con anuncios fusionadas, sin alquiler ni compra | — |
| Sinopsis sin notas de procedencia ("(Tomado de la página imdb)") | — |
| Columnas redundantes eliminadas: año dentro del título, fecha exacta, promedios duplicados, IDs de origen, tags | — |

## Uso en AWS (propuesta, aún no conectado)

| Data | Dónde | Quién la usa |
|---|---|---|
| `calificaciones` | Ningún lado: solo para entrenar offline | Script de entrenamiento |
| Catálogo + vectores del modelo | S3 (JSON + `.npy`), cargados en memoria al arrancar | Lambda de ML `/recomendar` (filtra y rankea) |
| Catálogo | DynamoDB `Peliculas` (PK `id`), consulta por llave | Herramientas del chat (detalle, registrar vista) |
| Datos del usuario | DynamoDB `Conversaciones`, `Perfil`, `Vistas`, `Recomendaciones` | Lambda del chat |

La búsqueda por nombre ("ya vi Interstellar") se hace en vivo contra la API externa (tolera errores de tipeo, títulos en español y estrenos recientes) y se traduce a nuestro `id` con `ids_externos`. La disponibilidad del snapshot sirve para filtrar; la de las 3 recomendaciones finales se confirma en vivo.

## Licencias y atribución
- MovieLens: uso no comercial, citar a Harper y Konstan (2015), no implicar respaldo de GroupLens.
- TMDB: uso no comercial con atribución ("This product uses the TMDB API but is not endorsed or certified by TMDB"); no se redistribuye su base (por eso `data/` no se versiona).
- Disponibilidad por plataforma: JustWatch (vía TMDB), con atribución en los créditos del frontend.

Aunque el dataset se presenta como uno solo, **los créditos de la interfaz y del informe deben citar las fuentes**: lo exigen las licencias.
