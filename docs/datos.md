# Datos: fuentes y consolidación

## Fuentes

### 1. MovieLens (GroupLens): calificaciones y catálogo base

| Dataset | Películas | Ratings | Cobertura | Zip | Uso |
|---|---|---|---|---|---|
| **ml-latest-small** (elegido) | 9,742 | 100,836 (610 usuarios) | 1996 – sept 2018 | ~0.98 MB | Entrenar similitud y catálogo del MVP |
| ml-32m (alternativa) | ~87,000 | 32 M (~200k usuarios) | hasta oct 2023 | ~239 MB | Solo si se necesitan títulos más recientes |

URL: `https://files.grouplens.org/datasets/movielens/ml-latest-small.zip`. Se descarga con un script y **no se sube al repo**.

Archivos: `movies.csv` (movieId, title con año, genres con `|`), `ratings.csv` (userId, movieId, rating 0.5–5, timestamp), `tags.csv`, `links.csv` (movieId, imdbId, tmdbId).

Licencia: uso de investigación, no comercial, citar a Harper y Konstan (2015), no implicar respaldo de GroupLens. Permite redistribuir bajo las mismas condiciones, pero por política del equipo no se suben los CSV.

### 2. TMDB API v3: metadatos y disponibilidad

Base `https://api.themoviedb.org/3`. Requiere API key o token de lectura (Bearer). El token de lectura vive en `~/.config/promptcorn/tmdb_token` (local, fuera del repo) o en la variable `TMDB_TOKEN`; en AWS irá en SSM Parameter Store. Probado: `/movie/862?append_to_response=watch/providers` devuelve detalle en español y plataformas PE en una sola llamada.

Lo que aporta y MovieLens no tiene: sinopsis, duración, póster, idioma, popularidad, puntaje, géneros de TMDB y plataformas por país (JustWatch).

## Cómo se unen

La llave de unión es `links.csv`:

```
movies.csv ──movieId──> links.csv ──tmdbId──> TMDB /movie/{tmdbId}
ratings.csv ─movieId──┘
```

`links.csv` trae `tmdbId` para casi todas las películas (unas pocas vienen vacías y se descartan o se resuelven con `/search/movie` por título + año).

## Plan de consolidación (pendiente del GO)

1. `scripts/descargar_movielens.py`: baja y descomprime el zip en `data/raw/` (ignorado por git).
2. `scripts/enriquecer_tmdb.py`: por cada `tmdbId` llama a
   `/movie/{id}?language=es-PE&append_to_response=watch/providers` (una sola llamada trae detalle y plataformas).
   - ~9.7k llamadas; con concurrencia moderada (TMDB limita alrededor de 40–50 req/s) toma unos minutos.
   - Respuestas crudas cacheadas en `data/raw/tmdb/` para no repetir llamadas.
3. `scripts/consolidar.py`: join `movies` ⨝ `links` ⨝ TMDB → `data/processed/catalogo.parquet` (y CSV/JSON para DynamoDB o S3).

### Esquema propuesto de `catalogo`

| Campo | Fuente | Nota |
|---|---|---|
| movieId | MovieLens | llave del modelo de ML |
| tmdbId | links.csv | llave hacia TMDB |
| imdbId | links.csv | |
| titulo | MovieLens / TMDB | `title` sin el año; TMDB da título en español |
| titulo_original | TMDB | |
| anio | regex sobre title | `\((\d{4})\)\s*$` |
| generos | MovieLens (`|` → lista) | también `generos_tmdb` |
| sinopsis | TMDB `overview` (es-PE, fallback en-US) | |
| duracion_min | TMDB `runtime` | para "algo corto" |
| idioma_original | TMDB | |
| poster_path | TMDB | |
| popularidad, vote_average, vote_count | TMDB | desempate y filtros |
| n_ratings, rating_promedio | agregado de ratings.csv | popularidad dentro de MovieLens |
| plataformas_pe | TMDB watch/providers `results.PE.flatrate` | lista de nombres/ids; snapshot con fecha |
| fecha_snapshot | script | la disponibilidad cambia con el tiempo |

`ratings.csv` **no** se mezcla en la tabla del catálogo: se usa por separado para entrenar los vectores de similitud (SVD) y para los agregados `n_ratings` y `rating_promedio`.

### Consideraciones
- **Disponibilidad viva vs snapshot**: el snapshot sirve para filtrar candidatos (F3) rápido; antes de mostrar, se puede confirmar con `ver_donde_ver` en vivo.
- **Repo público**: el catálogo enriquecido con TMDB no se sube (los términos de TMDB no permiten redistribuir su base). Se guarda en S3/DynamoDB y en `data/` local ignorado por git.
- **Atribución**: TMDB y JustWatch en la sección de créditos del frontend.
