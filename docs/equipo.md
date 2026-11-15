# Equipo y división del trabajo

Dos integrantes, división por capas. **El único punto de contacto son los contratos JSON de las herramientas** (qué recibe y qué devuelve cada una).

> **Un solo repo para todo el proyecto** (`PromptCorn`): backend, chat y frontend, cada parte en su carpeta. Lo administra la Persona A; B entra como colaborador.

## Persona A: datos, modelo de ML y herramientas del backend

- **Dataset:** descarga, limpieza y consolidación del catálogo (hecho: ver [datos.md](datos.md)).
- **Modelo de ML:** vectores de similitud entre películas calculados offline (SVD sobre la matriz de calificaciones) y la API de ML (`/recomendar`), que en producción solo usa numpy. Detalle en [modelo.md](modelo.md).
- **Herramientas que invoca el chat:** `recomendar`, `buscar_pelicula`, `ver_donde_ver`, `registrar_vista`, `guardar_plataformas`, `obtener_historial`. Contratos cerrados en [contratos.md](contratos.md).
- **Tablas DynamoDB propias:** `Vistas`, `Perfil`, `Recomendaciones`. El catálogo completo va en S3 ([datos.md](datos.md#uso-en-aws)).
- **Entregables:** colección de Postman (Parte C backend), diagrama de arquitectura AWS, región y su sustento, costos con calculator.aws (Parte B), README del backend con script o notebook de entrenamiento.
- **Pruebas:** escenarios Gherkin HU1–HU4.

## Persona B: conversación, frontend y documentación de producto

- **Lambda del chat** (orquestador): prompt del sistema, tool calling con Groq, memoria en la tabla `Conversaciones` (de B).
- **Frontend:** prototipo del chat web en `/frontend`, conectado a la API real.
- **Documentación:** Parte A completa (benchmark, historias de usuario, propuesta de valor, MVP); en la Parte B, el frontend y la descripción del workflow y las APIs.
- **Pruebas:** README del frontend y escenarios Gherkin HU5–HU8.

## Reglas para no bloquearse

- **Contratos primero.** B desarrolla contra simulaciones que devuelven un JSON fijo; A construye las versiones reales; se cambian las URLs por variables de entorno.
- **Propiedad de carpetas.** A es dueño de `/ml`, `/tools` y `/scripts`; B de `/chat` y `/frontend`. Cada uno en su rama, integración por pull request, sin editar lo del otro.
- **Una sola cuenta AWS con prefijos:** `promptcorn-tools-...` (A) y `promptcorn-chat-...` (B).
- **Secretos** (Groq, TMDB) en las variables de entorno de cada Lambda (Learner Lab no da acceso a SSM). Nada de llaves ni datos en el repo (es público).
- **Sincronización** de 15 minutos al mediodía y en la noche: qué está listo y qué falta.

## Plan por días (referencial)

| Día | Persona A | Persona B |
|---|---|---|
| Mié 11 | Dataset limpio, vectores, tablas DynamoDB | Contratos (con A), prototipo del frontend con datos simulados, Parte A |
| Jue 12 | `/recomendar` y herramientas de TMDB desplegadas | Lambda del chat con herramientas simuladas y memoria |
| Vie 13 | Herramientas de datos y colección Postman. **2 pm asesoría (ambos)** | Cambia simulaciones por herramientas reales, conecta el frontend |
| Sáb 14 | Integración conjunta (mañana); pruebas HU1–HU4 | Integración; pruebas HU5–HU8, ajuste del prompt |
| Dom 15 | Diagrama, región y costos | Parte B y pulido de la interfaz |
| Lun 16 | Evidencia Postman, README del backend | README del frontend; revisión cruzada |
| Mar 17 | **Entrega (23:59)** y ensayo | Entrega y ensayo |
| Mié 18 | Exposición 19h | Exposición 19h |

El estado real lo indica la Persona A cuando haga falta; ver [status.md](status.md).

## Puntos abiertos que tocan a la Persona A

- ~~Recomendaciones, notas y disponibilidad~~ **Decidido (A), falta avisarle a B:** `recomendar` lee las notas de `Vistas` y las plataformas de `Perfil` por su cuenta, filtra por disponibilidad en Perú (snapshot en memoria), guarda lo entregado en `Recomendaciones` y no repite lo recomendado en las últimas 24 h. El chat solo traduce el pedido a filtros ([contratos.md](contratos.md)).
- ~~ID de película~~ **Decidido:** contratos y tablas usan solo el `id` propio del catálogo; nunca IDs de las fuentes. Películas fuera del catálogo (p. ej. posteriores a 2018): propuesta, **no se agregan**; `buscar_pelicula` las identifica en vivo pero las marca `en_catalogo: false` y el bot lo explica de forma amable (coincide con HU8, "título no encontrado"). A confirmar con B.
- ~~Región~~ **Decidido:** us-east-1.
- ~~Despliegue~~ **Decidido:** cuenta AWS Academy (Learner Lab). El equipo despliega **a mano** desde la consola usando el código del repo; los agentes de IA no tocan AWS. Roles: `LabRole`.
- ~~Contratos y versión de Python~~ **Decidido:** contratos en [contratos.md](contratos.md); todas las Lambdas en **Python 3.14**. La consola ofrece hasta 3.15, pero los binarios (numpy, pydantic-core) están armados para 3.14.
