# Contratos de las APIs y tablas

Especificación OpenAPI: [`openapi.yaml`](openapi.yaml). Publicada como Swagger UI en `<sitio>/docs/` e importable en Postman (**Import → archivo**).

Punto de contacto entre el chat (B) y el backend (A). Las películas se identifican **solo con el `id` propio** del catálogo (entero).

Todo cuelga de una sola HTTP API (definida en `serverless.yml`): `POST /chat`, `POST /recomendar` y `POST /<herramienta>` para las otras 5. El chat recibe la URL base en `API_TOOLS_URL` (la pone el despliegue). Todas usan al usuario fijo de la app: el chat no manda el usuario.

| API | Ruta | Estado |
|---|---|---|
| `recomendar` | `POST /recomendar` | ✅ Implementado (`tools/recomendar/`) |
| `buscar_pelicula`, `ver_donde_ver`, `registrar_vista`, `guardar_plataformas`, `obtener_historial` | `POST /<herramienta>` | ✅ Implementado (`tools/herramientas/`, una sola Lambda) |
| Chat (B) | `POST /chat` (API del chat) | ✅ Implementado (`chat/`) |

**Errores, igual en todas:** `400` con `{"error": "...", ...}` cuando el request es inválido. Puede traer listas de valores válidos (`generos_validos`, `plataformas_validas`) para que el LLM corrija y reintente. `404` cuando el `id` no existe. `500` con `{"error": "..."}` ante una falla interna. El chat le pasa al LLM el body de los 400/404, así puede corregirse solo.

## `recomendar` (API del modelo de ML)

`POST /recomendar` por API Gateway (JSON en el body). También se puede invocar la Lambda `promptcorn-tools-recomendar` directamente, con el mismo JSON como evento.

**El chat no le pasa las notas del usuario.** `recomendar` las lee de `Vistas`, las plataformas de `Perfil` y lo ya recomendado de `Recomendaciones`. El chat solo traduce el pedido a filtros.

### Request (todo opcional)

| Campo | Tipo | Descripción |
|---|---|---|
| `cantidad` | int 1–5 | Cuántas devolver (por defecto 3) |
| `generos` | list[str] | Al menos uno de estos géneros. Vocabulario: Acción, Animación, Aventura, Bélica, Ciencia ficción, Comedia, Crimen, Documental, Drama, Familia, Fantasía, Historia, Misterio, Música, Película de TV, Romance, Suspenso, Terror, Western |
| `duracion_max` | int | Minutos |
| `anio_min`, `anio_max` | int | Rango de año de estreno |
| `plataformas` | list[str] | Solo para esta consulta, **reemplaza** las del perfil. `[]` = cualquier plataforma de Perú. Si se omite, se usan las de `Perfil`. Nombres canónicos de `plataformas.csv` |
| `parecido_a` | int | `id` de una película: modo "parecidas a X" |
| `orden` | `"relevancia"` \| `"reciente"` | Por defecto `relevancia`. `reciente`: de las 30 más afines, las de estreno más nuevo primero ("lo más reciente que me guste") |
| `excluir` | list[int] | Ids que no deben salir (además de los que se excluyen solos) |
| `repetir` | bool | Por defecto `false`. `true`: no excluye lo recomendado en las últimas 24 h (para afinar el pedido anterior: "solo una, la más reciente") |
| `guardar` | bool | Guardar en `Recomendaciones` (por defecto `true`; `false` para pruebas) |
| `usuario_id` | str | Solo en invocación directa (pruebas). Por API Gateway se ignora: siempre es el usuario fijo de la app (`USUARIO_ID`), porque la API no tiene autenticación |

**Se excluyen solas:** las películas vistas, las marcadas "no me interesa", las recomendadas en las últimas 24 h y las que no están en ninguna plataforma de Perú.

### Response 200

```json
{
  "modo": "perfil",
  "recomendaciones": [
    {
      "id": 8619,
      "titulo": "Mad Max: Furia en el camino",
      "anio": 2015,
      "plataformas": ["Prime Video", "Apple TV+", "HBO Max"],
      "generos": ["Acción", "Aventura", "Ciencia ficción"],
      "duracion_min": 120,
      "sinopsis": "Perseguido por su turbulento pasado, Mad Max cree que… (máx. ~300 caracteres)",
      "poster": "/ixSuKuBnSfHmyzZbcWCywOKZ6Ho.jpg",
      "afinidad": 0.375,
      "motivo": {"id": 8318, "titulo": "Interestelar", "calificacion": 5}
    }
  ],
  "avisos": [],
  "filtros_aplicados": {"duracion_max": 130, "plataformas": ["Netflix", "Prime Video"]},
  "modelo": {"fecha": "2026-11-13", "k": 64}
}
```

- **`modo`:**
  - `perfil`: según las notas del usuario.
  - `parecido`: modo `parecido_a`.
  - `arranque_en_frio`: el usuario aún no calificó nada; se ordena por popularidad dentro de los filtros.
- **`afinidad`:** coseno entre −1 y 1. Sirve para ordenar, no para mostrarse como porcentaje. Es `null` en arranque en frío.
- **`motivo`:** la película calificada que más pesó. En modo `parecido` es la película X. `null` en arranque en frío. `calificacion` es la nota que el usuario le dio (puede ser `null` en modo `parecido`).
- **`poster`:** ruta relativa. URL completa = `https://image.tmdb.org/t/p/w500` + `poster`.
- **`avisos`:** texto para que el LLM se lo explique al usuario. Casos:
  - no tiene plataformas guardadas;
  - ninguna película cumple los filtros (`recomendaciones: []`);
  - menos resultados de los pedidos;
  - la película de `parecido_a` no tiene datos suficientes (se recomienda según el perfil).

### Errores

| Código | Cuándo | Body |
|---|---|---|
| 400 | Request inválido | `{"error": "Valores no reconocidos en 'generos': ['Anime'].", "generos_validos": [...]}` (o `plataformas_validas`). Pensado para que el LLM corrija y reintente |
| 500 | Error interno | `{"error": "Error interno en el recomendador."}`. El detalle queda en CloudWatch |

Por invocación directa (sin API Gateway) el error llega como `{"error": ..., "status": 400}`.

## `buscar_pelicula`

Busca por título en vivo, así que tolera errores de tipeo, títulos en español o en inglés y estrenos recientes. Traduce cada resultado a nuestro `id`.

| Request | Tipo | |
|---|---|---|
| `titulo` | str | Obligatorio |
| `anio` | int | Opcional, para desambiguar |

```json
{"resultados": [
  {"id": 8318, "titulo": "Interestelar", "anio": 2014, "sinopsis": "…", "poster": "/….jpg", "en_catalogo": true},
  {"id": null, "titulo": "Oppenheimer", "anio": 2023, "sinopsis": "…", "poster": "/….jpg", "en_catalogo": false}
], "avisos": []}
```

- Devuelve hasta 5 resultados, del más al menos relevante. Si son varios, el bot pregunta cuál era.
- **`en_catalogo: false`** (y `id: null`): la película existe, pero no está en nuestro catálogo, que llega hasta 2018. No se puede registrar ni usar en `parecido_a`. El bot lo explica de forma amable y ofrece una alternativa por género (HU8).
- `resultados: []`: no se encontró nada con ese título.
- Si la búsqueda en vivo no encuentra nada del catálogo (por errores de tipeo como "intersteller" o "toy stori", o porque la API no responde), busca también en el catálogo local por similitud. Si la API no respondió, `avisos` lo dice.

## `ver_donde_ver`

| Request | Tipo | |
|---|---|---|
| `id` | int | Obligatorio |

```json
{"id": 8318, "titulo": "Interestelar", "plataformas": ["Prime Video", "HBO Max", "Claro Video"], "fecha": "2026-11-15", "avisos": []}
```

Disponibilidad **actual** en Perú, solo por suscripción o gratis. `plataformas: []` significa que hoy no está en ninguna plataforma de Perú. Si la consulta en vivo falla, devuelve la del catálogo: `fecha` es la de ese snapshot y `avisos` lo explica.

## `registrar_vista`

| Request | Tipo | |
|---|---|---|
| `id` | int | Obligatorio |
| `estado` | `"visto"` \| `"no_me_interesa"` | Por defecto `"visto"` |
| `calificacion` | number 0.5–5 (múltiplos de 0.5) | Opcional. **Es lo que alimenta el modelo**: el bot debe pedirla cuando el usuario dice que vio una película |

```json
{"ok": true, "id": 8318, "titulo": "Interestelar", "estado": "visto", "calificacion": 5}
```

Si la película ya estaba registrada, se reemplaza: sirve para corregir una nota.

## `guardar_plataformas`

| Request | Tipo | |
|---|---|---|
| `plataformas` | list[str] | Obligatorio. Se aceptan variantes ("netflix", "Amazon Prime", "HBO", "Disney Plus") y se normalizan al nombre canónico |
| `accion` | `"reemplazar"` \| `"agregar"` \| `"quitar"` | Por defecto `"reemplazar"` |

```json
{"ok": true, "plataformas": ["Netflix", "Prime Video"], "no_reconocidas": ["Cuevana"]}
```

`plataformas` devuelve la lista final del usuario. `no_reconocidas` son las que no se guardaron, para que el bot lo diga.

## `obtener_historial`

| Request | Tipo | |
|---|---|---|
| `tipo` | `"recomendaciones"` \| `"vistas"` \| `"todo"` | Por defecto `"todo"` |
| `limite` | int 1–50 | Por defecto 10 (por tipo), las más recientes primero |

```json
{
  "recomendaciones": [{"fecha": "2026-11-15T20:00:00Z", "id": 8619, "titulo": "Mad Max: Furia en el camino", "anio": 2015, "plataformas": ["Prime Video"], "motivo": {"id": 8318, "titulo": "Interestelar", "calificacion": 5}}],
  "vistas": [{"fecha": "2026-11-15T19:55:00Z", "id": 8318, "titulo": "Interestelar", "estado": "visto", "calificacion": 5}]
}
```

## `reiniciar_usuario` (no es herramienta del chat)

`POST /reiniciar_usuario` con `{"confirmar": "BORRAR"}` → `{"ok": true, "borrados": {"vistas": n, "recomendaciones": n, "perfil": 0|1}}`.

Borra todo lo del usuario fijo en `Vistas`, `Perfil` y `Recomendaciones`, y vuelve al arranque en frío. Lo usa el botón **Reiniciar perfil** del frontend, con un modal de confirmación; además, el frontend crea un `usuario_id` de chat nuevo para que la memoria también empiece de cero. El LLM no la conoce: no está en sus herramientas. Sin `confirmar` responde 400 y no borra nada.

## Chat (B → frontend)

`POST /chat` con `{"usuario_id": "<id local del navegador>", "mensaje": "texto"}` → `{"usuario_id": "...", "respuesta": "texto del bot"}`. Con `"depurar": true` también devuelve `traza`: cada llamada a Groq y cada herramienta con sus argumentos y resultado. Esa misma traza queda siempre en CloudWatch (`serverless logs -f chat`), una línea JSON por turno. Aquí `usuario_id` solo separa conversaciones en la memoria (`promptcorn-chat-conversaciones`). Las herramientas son de un solo usuario (`usuario-demo`).

La respuesta incluye siempre `peliculas`: las recomendaciones de la última llamada a `recomendar` de ese turno (máx. 5), o `[]` si no hubo. Cada una es `{"id": int, "titulo": str, "anio": int|null, "poster_url": str|null}`. `poster_url` es `https://image.tmdb.org/t/p/w342` + la ruta del póster de TMDB (`null` si no hay); lo carga el navegador desde el CDN de imágenes de TMDB, cuya atribución ya está en el pie de página. El frontend las muestra como un mensaje aparte con los pósters en fila. No se guardan en la memoria de la conversación. Si hay un límite de uso de Groq (`reintentar: true`), `peliculas` es `[]`.

## Tablas DynamoDB (de A)

Capacidad bajo demanda. Nombres con prefijo `promptcorn-tools-`. Un solo usuario, pero la PK `usuario_id` se mantiene para no atar el diseño a eso.

| Tabla | Llaves | Atributos | Escribe | Lee |
|---|---|---|---|---|
| `promptcorn-tools-vistas` | PK `usuario_id` (S), SK `pelicula_id` (N) | `estado` (`visto` / `no_me_interesa`), `calificacion` (N 0.5–5, opcional), `fecha` (S, ISO) | `registrar_vista` | `recomendar` |
| `promptcorn-tools-perfil` | PK `usuario_id` (S) | `plataformas` (L de S, nombres canónicos), `actualizado` (S) | `guardar_plataformas` | `recomendar` |
| `promptcorn-tools-recomendaciones` | PK `usuario_id` (S), SK `sk` (S, `"<fecha ISO>#<id>"`) | `fecha`, `pelicula_id`, `titulo`, `anio`, `plataformas`, `afinidad`, `modo`, `motivo` (M) | `recomendar` | `recomendar` (últimas 24 h), `obtener_historial` |
| `promptcorn-chat-conversaciones` (de B) | PK `usuario_id` (S), SK `mensaje_id` (S, `"<fecha ISO>#<uuid>"`) | `rol` (`user` / `assistant`), `contenido` | Lambda del chat | Lambda del chat (últimos 12 mensajes) |

La SK de `Recomendaciones` empieza por la fecha. Así, "lo recomendado desde X" y el historial ordenado salen de una sola consulta por rango, sin escanear la tabla.
