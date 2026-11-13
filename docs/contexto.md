# Contexto del proyecto: PromptCorn

## 1. Qué es este proyecto

Proyecto Final del curso Cloud Computing, Maestría en Ciencia de Datos e Inteligencia Artificial (CDIA V5), UTEC Posgrado, docente Geraldo Colchado. Equipo de 2 integrantes.

- Ejecución: 21-Oct-2026 al 17-Nov-2026.
- Entrega: martes 17-Nov-2026 23:59h.
- Exposición virtual: miércoles 18-Nov-2026 19h.
- Asesoría virtual: viernes de 2 a 3 pm (20 min por grupo, previa coordinación con el asistente).

Rúbrica (20 puntos): Parte A 5, Parte B 5, Parte C backend 4, Parte C frontend 4, exposición 2.

## 2. Qué pide el enunciado

El grupo elige una problemática real de una empresa existente o ficticia que se resuelva con un workflow agéntico de un nivel de autonomía dado:

| Nivel | Descripción |
|---|---|
| 1 | Automatización sin IA |
| 2 | IA generativa que exige instrucción en cada paso |
| 3 | Workflow agéntico de baja autonomía: un agente especializado ejecuta tareas específicas dentro de límites rígidos preestablecidos |
| 4 | Agentes orquestados en rutas predefinidas que consultan APIs, toman decisiones lógicas intermedias y notifican resultados |
| 5 | Agentes de elevada autonomía |

Solo se permiten Nivel 3 o Nivel 4. **Nosotros somos Nivel 3.**

Requisitos del Nivel 3: como mínimo 1 API de modelo de ML y 1 API de Groq con memoria conversacional. En ambos niveles, como mínimo 1 API con su propia base de datos. (El Nivel 4 usaría AWS Step Functions y Groq sin memoria; no es nuestro caso.)

### Parte A, Análisis (QUÉ)
- Nombre del workflow agéntico.
- Benchmark: herramientas del mercado (stack que no sea AWS) donde podría implementarse el workflow; mínimo 3 alternativas, en un cuadro comparativo que incluya AWS como cuarta alternativa.
- Qué tendrá el workflow: tipos de clientes o usuarios; funcionalidades con historias de usuario y criterios de aceptación en Gherkin (BDD); propuesta de valor; MVP.

### Parte B, Diseño del MVP (CÓMO)
- Prototipo web responsivo del frontend a partir del MVP (se permiten Figma Make, Lovable, etc.).
- Diseño del backend: pasos del workflow, nombre y funcionalidad de cada API, diseño de tablas NoSQL en DynamoDB.
- Diagrama de arquitectura de la solución en AWS serverless.
- Elegir y sustentar la región de AWS.
- Costos mensuales con calculator.aws.

### Parte C, Implementación del MVP en AWS
- Backend: workflow, APIs y BD serverless. Evidencia de uso desde Postman.
- Frontend: conectar el prototipo web con las APIs y/o el workflow.
- Enlaces a repositorios públicos de GitHub con el código fuente.

> El repositorio es público: no subir llaves de API ni datos con restricción de redistribución.

## 3. La propuesta: PromptCorn

PromptCorn (prompt + popcorn) es un chatbot conversacional de recomendación de películas, Nivel 3. Servicio de una empresa ficticia de recomendación para suscriptores de streaming.

Decisiones vigentes:
- Un solo usuario en el MVP: `userId` fijo, sin login ni múltiples cuentas.
- El MVP se despliega en AWS serverless (no corre localmente).
- Solo películas (sin series), porque el modelo se entrena con MovieLens.
- Toda la interacción es por chat; plataformas, películas vistas y calificaciones se registran conversando.

Rol de cada componente:
- **Groq** es solo el proveedor que ejecuta el LLM. El LLM interpreta el lenguaje natural, decide qué herramienta llamar y con qué parámetros (tool calling con lista cerrada de herramientas = Nivel 3) y redacta la respuesta final.
- **El LLM no recomienda por su cuenta**: solo recomienda títulos que devuelvan las herramientas. Quien produce el ranking es la **API de ML**.
- **La memoria conversacional vive en DynamoDB**: la Lambda del chat lee los últimos mensajes, los envía a Groq en cada llamada y guarda el turno nuevo al final.

## 4. Diseño general

Flujo de un mensaje: chat web → API Gateway → Lambda del chat (orquestador) → carga memoria desde DynamoDB → Groq con herramientas. Si el LLM pide una herramienta, la Lambda la ejecuta (API de ML, TMDB o DynamoDB) y vuelve a llamar a Groq con el resultado. Al final guarda el turno y responde. Sin herramienta (charla simple) → respuesta directa.

Componentes:
- **Frontend**: chat web responsivo (Lovable o Figma Make), con posibles pestañas de vistas y recomendaciones; hosting en S3 + CloudFront o Amplify.
- **Lambda del chat**: prompt del sistema, tool calling con Groq, memoria.
- **API de ML** (`/recomendar`): vectores de similitud entre películas calculados offline (p. ej. SVD sobre la matriz de calificaciones de MovieLens); en producción solo numpy (similitud coseno entre las películas bien calificadas por el usuario y el resto), sin scikit-learn. Se evalúa un híbrido: filtros del LLM acotan candidatos y el ML los ordena.
- **Herramientas** (borrador): `recomendar`, `buscar_pelicula` (TMDB), `ver_donde_ver` (TMDB), `registrar_vista`, `guardar_plataformas`, `obtener_historial`.
- **Tablas DynamoDB** (borrador): `Conversaciones`, `Vistas` (tmdbId, movieId, calificación, estado), `Perfil` (plataformas), `Recomendaciones` (fecha, título, plataforma).
- **Llaves de Groq y TMDB**: SSM Parameter Store (SecureString), nunca en el repo.

Abierto: región de AWS (us-east-1 vs sa-east-1), lenguaje de las Lambdas y herramienta de despliegue, contratos JSON de las herramientas, detalle del híbrido filtros + ML.

Reparto: persona 1 = datos, modelo de ML, herramientas de datos, diagrama de arquitectura y costos. Persona 2 = chat con Groq, frontend y Parte A. Punto de contacto: contratos JSON de las herramientas.

Plan por etapas: 0 fundaciones · 1 modelo de ML y `/recomendar` · 2 tablas y herramientas · 3 Lambda del chat con Groq · 4 frontend · 5 integración y pruebas Gherkin · 6 entregables (diagrama, costos, Postman, repos) · 7 cierre y ensayo.

## 5. Funcionalidades del MVP

| ID | Funcionalidad | Descripción |
|---|---|---|
| F1 | Registro de plataformas | El usuario indica sus servicios y el bot los guarda en su perfil |
| F2 | Recomendación conversacional | El bot pregunta género, ánimo y tiempo disponible, y recomienda |
| F3 | Filtro por disponibilidad | Solo títulos disponibles en las plataformas del usuario |
| F4 | Dónde verlo | Cada recomendación indica la plataforma |
| F5 | Refinar / más opciones | Otras opciones o ajustar un criterio sin reiniciar |
| F6 | Excluir títulos vistos | "Ya lo vi" / "no me interesa" |
| F7 | Historial | Consultar recomendaciones previas |
| F8 | Respuestas ambiguas | Repregunta y ofrece opciones |
| F9 | Registro de vistas | Títulos vistos con calificación opcional 1–5; se excluyen y alimentan los gustos |

Fuera del MVP: F10 por elenco, F11 login/multi-cuenta, F12 series. Posibles: "algo parecido a X" (similitud directa del modelo) y watchlist (estado más en `Vistas`).

## 6. Historias de usuario (Gherkin, resumidas)

- **HU1 (F1) Registrar mis plataformas.** Usuario nuevo: el bot pregunta plataformas; "Netflix y Prime Video" → guarda y confirma "Registré Netflix y Prime Video". Recurrente: "ya no tengo Netflix, ahora tengo Max" → elimina Netflix, agrega Max.
- **HU2 (F2) Recomendación a mi medida.** Con ≥1 plataforma, responde género, ánimo y tiempo → 3 recomendaciones con título, año, sinopsis breve y motivo. "Quiero una película de suspenso corta" → no repregunta lo ya dado.
- **HU3 (F3, F4) Solo mis plataformas.** Con Netflix y Max, todas disponibles en una de ellas y se indica cuál. Sin coincidencias exactas → lo informa y propone relajar un criterio.
- **HU4 (F5) Otras opciones.** "Dame otras opciones" → 3 nuevas distintas. "Mejor algo de comedia" → mantiene los demás criterios.
- **HU5 (F6) No recibir lo que ya vi.** "Ya la vi" sobre "Shutter Island" → registrada como vista y excluida.
- **HU6 (F7) Historial.** Con historial: títulos con fecha y plataforma. Sin historial: lo indica y ofrece iniciar una.
- **HU7 (F8) Que me entienda.** Respuesta que no es un género → reformula y ofrece acción, comedia, drama, suspenso o terror.
- **HU8 (F9) Registrar lo que vi.** "Ya vi Interstellar, le doy 5" → "Registré Interstellar con 5 estrellas". Varios títulos → registra y pregunta si califica. Título ambiguo ("Dune") → opciones con año. No encontrado → pide verificar. Calificaciones altas de ciencia ficción → prioriza ciencia ficción y lo explica.

## 7. Datos externos

Ver [datos.md](datos.md) para el detalle y el plan de consolidación.

- **MovieLens ml-latest-small** (GroupLens): 100,836 ratings, 3,683 tags, 9,742 películas, 610 usuarios; hasta sept-2018. `movies.csv`, `ratings.csv`, `tags.csv`, `links.csv` (puente a TMDB). No trae sinopsis, duración, póster ni plataformas. Citar Harper y Konstan (2015).
- **TMDB API v3**: `/search/movie`, `/movie/{id}`, `/discover/movie`, `/movie/{id}/watch/providers` (región PE), `/watch/providers/movie?watch_region=PE`. Gratuita no comercial con atribución a TMDB; la disponibilidad viene de JustWatch y exige atribuirlo.
- **Groq API**: compatible con OpenAI chat completions (`https://api.groq.com/openai/v1`), tool calling, sin estado. Verificar modelos y límites al implementar.

## 8. Limitaciones conocidas del MVP
- MovieLens llega hasta 2018; el modelo de ML solo usa películas con `movieId`. Películas recientes se buscan en TMDB y se guardan con `tmdbId`, pero no influyen en el ranking.
- La disponibilidad por plataforma depende de TMDB/JustWatch para Perú y puede estar incompleta; si no se confirma, se informa en lugar de bloquear.
- Un solo usuario, sin autenticación.
