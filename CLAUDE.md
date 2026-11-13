# CLAUDE.md

Guía para agentes de IA que trabajen en este repo.

## Proyecto
PromptCorn: chatbot de recomendación de películas (workflow agéntico Nivel 3) para el Proyecto Final de Cloud Computing, Maestría CDIA (UTEC). Entrega: 17-Nov-2026 23:59h.

- Contexto completo: [docs/contexto.md](docs/contexto.md)
- Datos y consolidación: [docs/datos.md](docs/datos.md)
- Equipo y división del trabajo: [docs/equipo.md](docs/equipo.md)
- Status y TODOs: [docs/status.md](docs/status.md). **Actualízalo al terminar una tarea.**

## Rol
El usuario es la **Persona A**: datos, modelo de ML, herramientas del backend y este repo (dueño de `/ml`, `/tools`, `/scripts`). La Persona B lleva el chat (`/chat`), el frontend (repo aparte) y la Parte A. No editar lo de B; el punto de contacto son los contratos JSON de las herramientas. Recursos AWS de A con prefijo `promptcorn-tools-`.

## Reglas
- **El repo es público.** Nunca subir llaves (Groq, TMDB, AWS), `.env`, ni datos crudos o enriquecidos (`data/` está en `.gitignore`). Las llaves van en SSM Parameter Store.
- No subir CSV de MovieLens ni respuestas de TMDB: se regeneran con los scripts.
- El LLM no recomienda por su cuenta: solo títulos devueltos por la API de ML / herramientas.
- Solo películas, un solo usuario (`userId` fijo), todo por chat.
- Idioma de docs y UI: español.

## Git / GitHub
- Remote: `https://github.com/shadow-maker/PromptCorn.git` (HTTPS con keychain). Rama `main`.
- No usar `gh` (se cuelga pidiendo autenticación). Solo `git` CLI.
- Solo se tiene permiso sobre este repo: no tocar otros repos, no borrar nada, no cambiar accesos.
