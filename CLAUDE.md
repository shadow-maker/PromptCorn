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
El usuario es la **Persona A**: datos, modelo de ML, herramientas del backend y este repo (dueño de `/ml`, `/tools`, `/scripts`). La Persona B lleva el chat (`/chat`), el frontend (repo aparte) y la Parte A. No editar lo de B; el punto de contacto son los contratos JSON de las herramientas. Recursos AWS de A con prefijo `promptcorn-tools-`.

## Cómo trabajar con el usuario
- Las preguntas del usuario ("¿por qué X?", "¿no sería mejor Y?") **no son necesariamente pedidos de cambio**. Responde con el razonamiento, defiende la decisión si sigue siendo la mejor y cambia solo si el argumento lo justifica. Debatir está bien; ceder por reflejo no.

## Reglas
- **El repo es público.** Nunca subir llaves (Groq, TMDB, AWS), `.env`, ni datos crudos o enriquecidos (`data/` está en `.gitignore`). Las llaves van en SSM Parameter Store.
- No subir CSV de MovieLens ni respuestas de TMDB: se regeneran con los scripts.
- El LLM no recomienda por su cuenta: solo títulos devueltos por la API de ML / herramientas.
- Solo películas, un solo usuario (`userId` fijo), todo por chat.
- **IDs de película:** en contratos, tablas y respuestas se usa solo el `id` propio del catálogo. Nunca exponer IDs de las fuentes (la traducción queda interna en las herramientas).
- **AWS:** cuenta AWS Academy (Learner Lab). Los agentes **no tocan AWS**: el equipo despliega a mano desde la consola. Entregar código y artefactos listos para subir (zips, layers, guías paso a paso), usando `LabRole`, región us-east-1.
- Idioma de docs y UI: español.

## Git / GitHub
- Remote: `https://github.com/shadow-maker/PromptCorn.git` (HTTPS con keychain). Rama `main`.
- No usar `gh` (se cuelga pidiendo autenticación). Solo `git` CLI.
- Solo se tiene permiso sobre este repo: no tocar otros repos, no borrar nada, no cambiar accesos.
