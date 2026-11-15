# Status y TODOs

Última actualización: 2026-11-13. Entrega: **martes 17-Nov-2026 23:59h** · Exposición: miércoles 18-Nov-2026 19h.

Responsable: **A** = Persona A (datos, ML, herramientas, este repo) · **B** = Persona B (chat, frontend, Parte A) · **A+B** = ambos. Ver [equipo.md](equipo.md).

## Resumen por etapa

| # | Etapa | Responsable | Estado |
|---|---|---|---|
| 0 | Fundaciones (repo, datos, llaves, accesos, contratos) | A+B | 🟡 En curso |
| 1 | Modelo de ML y `/recomendar` | A | 🟢 Código listo; falta desplegar en AWS ([guía](despliegue.md)) |
| 2 | Tablas DynamoDB y herramientas | A | 🟢 Código listo; falta desplegar |
| 3 | Lambda del chat con Groq | B | 🟢 Código listo e integrado con el contrato; falta desplegar |
| 4 | Frontend | B | 🟡 Funciona en modo demostración; falta conectar y alojar |
| 5 | Integración y pruebas Gherkin | A+B | ⚪ Pendiente |
| 6 | Entregables (diagrama, región, costos, Postman, READMEs, Partes A y B) | A+B | ⚪ Pendiente |
| 7 | Cierre y ensayo | A+B | ⚪ Pendiente |

## Etapa 0: Fundaciones
- [x] (A) Documentación base (`README.md`, `CLAUDE.md`, `docs/`).
- [x] (A) Repo público en GitHub (único para todo el proyecto).
- [ ] (A) Agregar a B como colaborador del repo (Settings → Collaborators).
- [x] (A) Token de lectura de TMDB (local en `~/.config/promptcorn/tmdb_token`, fuera del repo).
- [x] (A) Datos descargados: MovieLens ml-latest-small + TMDB (snapshot de disponibilidad PE del 2026-11-12).
- [x] (A) Catálogo consolidado con ID propio: 9,649 películas y 100,612 calificaciones ([datos.md](datos.md)).
- [ ] (A) Compartir datos con B por Drive ([qué compartir](datos.md#compartir-con-la-persona-b)).
- [x] (A+B) Contratos JSON de las 6 herramientas y del chat ([contratos.md](contratos.md)). El chat ya los usa.
- [ ] (B) API key de Groq; verificar modelos con tool calling y límites del plan gratuito.
- [ ] (A+B) Accesos a la cuenta AWS y convención de prefijos.
- [x] (A) Región AWS: us-east-1 (falta redactar el sustento para el informe).
- [x] (A+B) Despliegue manual desde la consola de AWS Academy (Learner Lab, `LabRole`); Lambdas en Python.
- [x] (A+B) Versión de Python: **3.14** en todas las Lambdas. Learner Lab ofrece hasta 3.15; se usa 3.14 porque los zips y la layer están armados para esa versión.

## Etapa 1: Modelo de ML (A)
- [x] Scripts de descarga y consolidación (`scripts/`).
- [x] Entrenar vectores de similitud (SVD k=64) offline: `ml/entrenar.py` → `ml/artefactos/` ([modelo.md](modelo.md)).
- [x] Evaluación (split temporal por usuario): Recall@10 0.182 vs 0.125 del baseline "lo más visto" (+46 %).
- [x] Núcleo del recomendador (`tools/recomendar/recomendador.py`): filtros, perfil, "parecida a X", arranque en frío, motivo.
- [x] Lambda `/recomendar`: `handler.py` (artefactos de S3; lee `Vistas`, `Perfil` y `Recomendaciones`; guarda lo entregado), pruebas, `empaquetar.sh` (zip + layer de numpy) y eventos de prueba.
- [x] Contrato de `recomendar` y esquema de las tablas ([contratos.md](contratos.md)).
- [ ] (A+B) Desplegar en Learner Lab siguiendo [despliegue.md](despliegue.md): S3, 3 tablas, layer, Lambda, API Gateway.
- [ ] Pasarle a B la URL de `/recomendar` y el contrato.

## Etapa 2: Tablas y herramientas (A)
- [x] Esquema de las tablas `Vistas`, `Perfil`, `Recomendaciones` ([contratos.md](contratos.md)).
- [x] Lambda `promptcorn-tools-herramientas` (`tools/herramientas/`): `buscar_pelicula` (en vivo, tolera tipeo, `en_catalogo`), `ver_donde_ver` (en vivo con respaldo al snapshot), `registrar_vista`, `guardar_plataformas` (normaliza nombres), `obtener_historial`. Incluye 20 pruebas, eventos y `empaquetar.sh`.
- [x] Catálogo completo para S3 (`scripts/exportar_catalogo.py`, 6.1 MB) en lugar de una tabla `Peliculas`.
- [ ] (A+B) Desplegar: catálogo en S3, token en SSM, Lambda y ruta `POST /{herramienta}` ([despliegue.md](despliegue.md#herramientas-buscar_pelicula-ver_donde_ver-registrar_vista-guardar_plataformas-obtener_historial)).
- [ ] Probar el flujo completo con el chat real: `MOCK_MODE=false` y `API_TOOLS_URL`.
- [ ] Colección de Postman con evidencia de cada herramienta.

## Etapa 3: Lambda del chat (B)
- [x] Prompt del sistema, tool calling con Groq (hasta 5 vueltas), memoria en `Conversaciones`, errores de herramientas devueltos al LLM.
- [x] Simulaciones con el formato del contrato (`MOCK_MODE=true`); modo real con una sola URL base (`API_TOOLS_URL`).
- [x] Integrado a `main` y alineado al contrato (definiciones de herramientas, prompt, key de Groq desde SSM).
- [ ] Desplegar la Lambda del chat y su API ([despliegue.md](despliegue.md#chat-persona-b)).
- [ ] Probar con Groq real (modelo por defecto `openai/gpt-oss-20b`).

## Etapa 4: Frontend (B)
- [x] Prototipo en `/frontend` (React + Vite), en modo demostración si no hay `VITE_API_URL`.
- [ ] Conectar con la API del chat.
- [ ] Hosting en S3 + CloudFront o Amplify.
- [ ] Créditos en la interfaz: TMDB, JustWatch y MovieLens (obligatorio por licencia; aún no están).

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

## Decisiones tomadas
- Artefactos del modelo (vectores + catálogo del modelo) en **S3**; la Lambda los carga al arrancar.
- `recomendar` excluye lo ya recomendado **en el último día** (para que "dame otras opciones" traiga títulos nuevos).
- `recomendar` lee por su cuenta las notas (`Vistas`) y las plataformas (`Perfil`), filtra por disponibilidad en Perú y guarda lo entregado en `Recomendaciones`. El chat solo manda filtros (ya integrado en `chat/`).
- Contratos JSON de las 6 herramientas y del chat cerrados ([contratos.md](contratos.md)).
- Películas fuera del catálogo: `buscar_pelicula` las devuelve con `id: null` y `en_catalogo: false`; no se agregan.
- Las 5 herramientas de datos van en una sola Lambda (`POST /{herramienta}`) y `recomendar` va aparte, porque usa numpy y el modelo.
- El catálogo completo va en S3 como JSON en memoria; no hay tabla `Peliculas`. Las bases de datos del enunciado son las 4 tablas DynamoDB.
- Un solo bucket `promptcorn-tools-datos-<sufijo>`, con los prefijos `modelo/` y `catalogo/`.
