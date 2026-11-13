# Status y TODOs

Última actualización: 2026-11-12. Entrega: **martes 17-Nov-2026 23:59h** · Exposición: miércoles 18-Nov-2026 19h.

## Hecho
- [x] Documentación base del proyecto (`README.md`, `CLAUDE.md`, `docs/`).
- [x] Repositorio Git y remote público en GitHub.
- [x] Investigación de fuentes de datos y plan de consolidación ([datos.md](datos.md)).

## Etapa 0: Fundaciones
- [ ] GO para descargar MovieLens ml-latest-small.
- [ ] Obtener API key / token de lectura de TMDB.
- [ ] Obtener API key de Groq; verificar modelos con tool calling y límites del plan gratuito.
- [ ] Accesos AWS del equipo.
- [ ] Decidir región AWS (us-east-1 vs sa-east-1).
- [ ] Decidir lenguaje de las Lambdas y herramienta de despliegue (SAM / Serverless Framework / CDK).
- [ ] Definir contratos JSON de las herramientas.

## Etapa 1: Datos y modelo de ML
- [ ] Script de descarga de MovieLens.
- [ ] Enriquecimiento con TMDB (detalle + watch/providers PE).
- [ ] Consolidar catálogo (join MovieLens ⨝ links ⨝ TMDB).
- [ ] Entrenar vectores de similitud (SVD) offline y exportar `.npy`.
- [ ] Lambda `/recomendar` (numpy, similitud coseno).

## Etapa 2: Tablas y herramientas
- [ ] Tablas DynamoDB: Conversaciones, Vistas, Perfil, Recomendaciones.
- [ ] Herramientas: recomendar, buscar_pelicula, ver_donde_ver, registrar_vista, guardar_plataformas, obtener_historial.
- [ ] Llaves en SSM Parameter Store (SecureString).

## Etapa 3: Lambda del chat
- [ ] Prompt del sistema, tool calling con Groq, memoria en DynamoDB, reintento si el JSON falla.

## Etapa 4: Frontend
- [ ] Prototipo (Lovable / Figma Make) y conexión con API Gateway.
- [ ] Hosting en S3 + CloudFront o Amplify; créditos TMDB y JustWatch.

## Etapa 5–7: Integración, entregables, cierre
- [ ] Pruebas con los escenarios Gherkin (HU1–HU8).
- [ ] Colección Postman con evidencia.
- [ ] Diagrama de arquitectura AWS.
- [ ] Costos con calculator.aws.
- [ ] Parte A: benchmark (3 alternativas + AWS), usuarios, propuesta de valor, MVP.
- [ ] Ensayo de la exposición.

## Decisiones abiertas
- Región AWS.
- Lenguaje de Lambdas y herramienta de despliegue.
- Contratos JSON de las herramientas.
- Detalle del híbrido filtros del LLM + ranking del ML.
- ¿ml-latest-small (2018) o ml-32m (2023)? Por defecto: small.
