# Status y TODOs

Última actualización: 2026-11-12. Entrega: **martes 17-Nov-2026 23:59h** · Exposición: miércoles 18-Nov-2026 19h.

Responsable: **A** = Persona A (datos, ML, herramientas, este repo) · **B** = Persona B (chat, frontend, Parte A) · **A+B** = ambos. Ver [equipo.md](equipo.md).

## Resumen por etapa

| # | Etapa | Responsable | Estado |
|---|---|---|---|
| 0 | Fundaciones (repo, datos, llaves, accesos, contratos) | A+B | 🟡 En curso |
| 1 | Modelo de ML y `/recomendar` | A | 🟡 En curso (datos listos; falta modelo y API) |
| 2 | Tablas DynamoDB y herramientas | A | ⚪ Pendiente |
| 3 | Lambda del chat con Groq | B | ❔ A confirmar con B |
| 4 | Frontend | B | ❔ A confirmar con B |
| 5 | Integración y pruebas Gherkin | A+B | ⚪ Pendiente |
| 6 | Entregables (diagrama, región, costos, Postman, READMEs, Partes A y B) | A+B | ⚪ Pendiente |
| 7 | Cierre y ensayo | A+B | ⚪ Pendiente |

## Etapa 0: Fundaciones
- [x] (A) Documentación base (`README.md`, `CLAUDE.md`, `docs/`).
- [x] (A) Repo del backend público en GitHub.
- [x] (A) Token de lectura de TMDB (local en `~/.config/promptcorn/tmdb_token`, fuera del repo).
- [x] (A) Datos descargados: MovieLens ml-latest-small + TMDB (snapshot de disponibilidad PE del 2026-11-12).
- [x] (A) Catálogo consolidado con ID propio: 9,649 películas y 100,612 calificaciones ([datos.md](datos.md)).
- [ ] (A) Compartir datos con B por Drive ([qué compartir](datos.md#compartir-con-la-persona-b)).
- [ ] (A+B) Contratos JSON de las herramientas (ID de película = `id` propio, ya decidido).
- [ ] (B) API key de Groq; verificar modelos con tool calling y límites del plan gratuito.
- [ ] (A+B) Accesos a la cuenta AWS y convención de prefijos.
- [x] (A) Región AWS: us-east-1 (falta redactar el sustento para el informe).
- [x] (A+B) Despliegue manual desde la consola de AWS Academy (Learner Lab, `LabRole`); Lambdas en Python.
- [ ] (A+B) Versión de Python: confirmar en la consola si existe el runtime 3.14 (si no, 3.13).

## Etapa 1: Modelo de ML (A)
- [x] Scripts de descarga y consolidación (`scripts/`).
- [ ] Entrenar vectores de similitud (SVD) offline, script o notebook en `/ml`, exportar `.npy`.
- [ ] Evaluación simple del modelo (p. ej. split por fecha) para el informe.
- [ ] Lambda `/recomendar` (numpy, similitud coseno, filtros y exclusiones).

## Etapa 2: Tablas y herramientas (A)
- [ ] Tablas DynamoDB: `Vistas`, `Perfil`, `Recomendaciones` (+ `Peliculas` si se adopta).
- [ ] Herramientas en `/tools`: `recomendar`, `buscar_pelicula`, `ver_donde_ver`, `registrar_vista`, `guardar_plataformas`, `obtener_historial`.
- [ ] Token de TMDB en SSM Parameter Store (SecureString).
- [ ] Colección de Postman con evidencia de cada herramienta.

## Etapa 3: Lambda del chat (B)
- [ ] Prompt del sistema, tool calling con Groq, memoria en `Conversaciones`, reintento si el JSON falla.
- [ ] Desarrollo contra simulaciones → cambio a URLs reales por variables de entorno.

## Etapa 4: Frontend (B)
- [ ] Prototipo (Lovable / Figma Make) y conexión con API Gateway.
- [ ] Hosting en S3 + CloudFront o Amplify; créditos a TMDB, JustWatch y MovieLens.

## Etapa 5: Integración y pruebas (A+B)
- [ ] (A) Escenarios Gherkin HU1–HU4.
- [ ] (B) Escenarios Gherkin HU5–HU8.

## Etapa 6: Entregables
- [ ] (A) Diagrama de arquitectura AWS serverless.
- [ ] (A) Región y su sustento.
- [ ] (A) Costos mensuales con calculator.aws.
- [ ] (A) README del backend con el script de entrenamiento.
- [ ] (B) Parte A: benchmark (3 alternativas + AWS), usuarios, historias de usuario, propuesta de valor, MVP.
- [ ] (B) Parte B: frontend, workflow y APIs. README del frontend.
- [ ] (A+B) Revisión cruzada.

## Etapa 7: Cierre (A+B)
- [ ] Entrega (martes 17, 23:59).
- [ ] Ensayo y exposición (miércoles 18, 19h).

## Decisiones abiertas
- Contratos JSON de las herramientas.
- `id` para películas fuera del catálogo (posteriores a 2018) encontradas en vivo.
- Versión de Python de las Lambdas (3.13 o 3.14).
- ¿Quién escribe en `Recomendaciones`? ¿Quién filtra por disponibilidad? (propuesta: `recomendar` en ambos casos).
- Detalle del híbrido filtros del LLM + ranking del ML.
- Arquitectura de datos en AWS (propuesta en [datos.md](datos.md#uso-en-aws-propuesta-aún-no-conectado)): catálogo en S3 para el ML + DynamoDB `Peliculas` para consultas por llave.
