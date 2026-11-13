# Contratos de las herramientas y tablas (Persona A)

Punto de contacto entre el chat (B) y el backend (A). Las películas se identifican **solo con el `id` propio** del catálogo.

| Herramienta | Estado del contrato |
|---|---|
| `recomendar` | ✅ Implementado (`tools/recomendar/`) |
| `buscar_pelicula`, `ver_donde_ver`, `registrar_vista`, `guardar_plataformas`, `obtener_historial` | Borrador en [equipo.md](equipo.md) |

## `recomendar` (API del modelo de ML)

`POST /recomendar` por API Gateway (JSON en el body). También se puede invocar la Lambda `promptcorn-tools-recomendar` directamente, con el mismo JSON como evento.

**El chat no le pasa las notas del usuario.** `recomendar` las lee de `Vistas`, las plataformas de `Perfil` y lo ya recomendado de `Recomendaciones`. El chat solo traduce el pedido a filtros.

### Request (todo opcional)

| Campo | Tipo | Descripción |
|---|---|---|
| `cantidad` | int 1–10 | Cuántas devolver (por defecto 3) |
| `generos` | list[str] | Al menos uno de estos géneros. Vocabulario: Acción, Animación, Aventura, Bélica, Ciencia ficción, Comedia, Crimen, Documental, Drama, Familia, Fantasía, Historia, Misterio, Música, Película de TV, Romance, Suspenso, Terror, Western |
| `duracion_max` | int | Minutos |
| `anio_min`, `anio_max` | int | Rango de año de estreno |
| `plataformas` | list[str] | Solo para esta consulta, **reemplaza** las del perfil. `[]` = cualquier plataforma de Perú. Si se omite, se usan las de `Perfil`. Nombres canónicos de `plataformas.csv` |
| `parecido_a` | int | `id` de una película: modo "parecidas a X" |
| `excluir` | list[int] | Ids que no deben salir (además de los que se excluyen solos) |
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

## Tablas DynamoDB (de A)

Capacidad bajo demanda. Nombres con prefijo `promptcorn-tools-`. Un solo usuario, pero la PK `usuario_id` se mantiene para no atar el diseño a eso.

| Tabla | Llaves | Atributos | Escribe | Lee |
|---|---|---|---|---|
| `promptcorn-tools-vistas` | PK `usuario_id` (S), SK `pelicula_id` (N) | `estado` (`visto` / `no_me_interesa`), `calificacion` (N 0.5–5, opcional), `fecha` (S, ISO) | `registrar_vista` | `recomendar` |
| `promptcorn-tools-perfil` | PK `usuario_id` (S) | `plataformas` (L de S, nombres canónicos), `actualizado` (S) | `guardar_plataformas` | `recomendar` |
| `promptcorn-tools-recomendaciones` | PK `usuario_id` (S), SK `sk` (S, `"<fecha ISO>#<id>"`) | `fecha`, `pelicula_id`, `titulo`, `anio`, `plataformas`, `afinidad`, `modo`, `motivo` (M) | `recomendar` | `recomendar` (últimas 24 h), `obtener_historial` |

La SK de `Recomendaciones` empieza por la fecha. Así, "lo recomendado desde X" y el historial ordenado salen de una sola consulta por rango, sin escanear la tabla.
