# CLAUDE.md

Guía para agentes de IA que trabajen en este repo.

## Proyecto
PromptCorn: chatbot de recomendación de películas (workflow agéntico Nivel 3) para el Proyecto Final de Cloud Computing, Maestría CDIA (UTEC). Entrega: 17-Nov-2026 23:59h.

- Contexto completo: [docs/contexto.md](docs/contexto.md)
- Datos y consolidación: [docs/datos.md](docs/datos.md)
- Modelo de ML (diseño, evaluación, artefactos): [docs/modelo.md](docs/modelo.md)
- Equipo y división del trabajo: [docs/equipo.md](docs/equipo.md)
- Status y TODOs: [docs/status.md](docs/status.md). **Actualízalo al terminar una tarea.**

## Rol
El usuario es la **Persona A**: datos, modelo de ML, herramientas del backend y este repo (dueño de `/ml`, `/tools`, `/scripts`). La Persona B lleva el chat (`/chat`), el frontend (`/frontend`) y la Parte A. Todo el proyecto vive en este único repo. No editar lo de B; el punto de contacto son los contratos JSON de las herramientas. Recursos AWS de A con prefijo `promptcorn-tools-`.

## Cómo trabajar con el usuario
- Las preguntas del usuario ("¿por qué X?", "¿no sería mejor Y?") **no son necesariamente pedidos de cambio**. Responde con el razonamiento, defiende la decisión si sigue siendo la mejor y cambia solo si el argumento lo justifica. Debatir está bien; ceder por reflejo no.

## Reglas
- **El repo es público.** Nunca subir llaves (Groq, TMDB, AWS), `.env`, ni datos crudos o enriquecidos (`data/` está en `.gitignore`). Las llaves viven en `~/.promptcorn.env` de la EC2 de despliegue y el despliegue las pasa a las variables de entorno de las Lambdas (Learner Lab no da acceso a SSM).
- No subir CSV de MovieLens ni respuestas de TMDB: se regeneran con los scripts.
- El LLM no recomienda por su cuenta: solo títulos devueltos por la API de ML / herramientas.
- Solo películas, un solo usuario (`userId` fijo), todo por chat.
- **IDs de película:** en contratos, tablas y respuestas se usa solo el `id` propio del catálogo. Nunca exponer IDs de las fuentes (la traducción queda interna en las herramientas).
- **AWS:** cuenta AWS Academy (Learner Lab). Los agentes **no tocan AWS**: el equipo despliega. Infraestructura como código en `serverless.yml` (Serverless Framework v4.46, cuenta con org), desplegada con `despliegue/desplegar.sh` (git pull + empaquetado + `serverless deploy` + frontend) desde una EC2 de despliegue con `LabInstanceProfile`. Ver [docs/despliegue.md](docs/despliegue.md). `LabRole`, región us-east-1, Python 3.14.
- Idioma de docs y UI: español.

## Git / GitHub
- Remote: `https://github.com/shadow-maker/PromptCorn.git` (HTTPS con keychain). Rama `main`.
- No usar `gh` (se cuelga pidiendo autenticación). Solo `git` CLI.
- Solo se tiene permiso sobre este repo: no tocar otros repos, no borrar nada, no cambiar accesos.
