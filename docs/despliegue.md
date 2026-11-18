# Despliegue en AWS Academy (Learner Lab) con Serverless Framework

Toda la infraestructura está en [`serverless.yml`](../serverless.yml): 3 Lambdas, la layer de numpy, una HTTP API con CORS, 4 tablas DynamoDB y el bucket del frontend. Se despliega con **Serverless Framework v4.46.0** (cuenta de serverless.com con org) desde una **EC2 de despliegue**, con un solo comando: `despliegue/desplegar.sh`.

- Región **us-east-1**, rol **`LabRole`** (Learner Lab no deja crear roles) y runtime **Python 3.14**.
- **Secretos** (token de la API de metadatos y key de Groq): viven en `~/.promptcorn.env` de la EC2, fuera del repo. El despliegue los pasa a las variables de entorno de las Lambdas. Learner Lab no da acceso a SSM; en producción irían en SSM o Secrets Manager.
- **La EC2 solo se usa para desplegar.** La app es 100 % serverless, así que no va en el diagrama de arquitectura.
- **El modelo y el catálogo** se suben aparte desde tu máquina, porque los datos no están en el repo por la licencia. Van al bucket que ya existe, `utec-promptcorn-tools-datos`.
- Los agentes de IA no tocan AWS: esta guía es para el equipo.

```
GitHub ──git pull──► EC2 (desplegar.sh: empaqueta + serverless deploy) ──CloudFormation──► Lambdas, layer, API, tablas, bucket web
Tu máquina (data/) ──modelo y catálogo──────────────────────────────────────────────────► S3 utec-promptcorn-tools-datos
```

| Recurso | Nombre |
|---|---|
| Stack de CloudFormation | `promptcorn-prod` |
| Lambdas | `promptcorn-tools-recomendar`, `promptcorn-tools-herramientas`, `promptcorn-chat` |
| Layer | `promptcorn-tools-numpy` |
| API (una sola) | `POST /chat`, `POST /recomendar`, `POST /{herramienta}` |
| Tablas | `promptcorn-tools-vistas`, `promptcorn-tools-perfil`, `promptcorn-tools-recomendaciones`, `promptcorn-chat-conversaciones` |
| Buckets | `utec-promptcorn-tools-datos` (ya existe) y `utec-promptcorn-chat-web` (lo crea el despliegue) |

---

## Parte 0. Antes de empezar (en tu máquina)

1. **Org de Serverless.** En `serverless.yml`, reemplaza `REEMPLAZAR_CON_TU_ORG` por el nombre de tu org. Lo ves en [app.serverless.com](https://app.serverless.com), arriba a la izquierda. No es secreto. Después:
   ```bash
   git commit -am "serverless.yml: org" && git push
   ```
2. **Si ya creaste a mano recursos con estos nombres** (tablas, Lambdas, APIs o el bucket web), bórralos: CloudFormation no puede crear algo que ya existe. Revisa también CloudWatch → Log groups `/aws/lambda/promptcorn-*`. **No borres `utec-promptcorn-tools-datos`.**
3. **Modelo y catálogo:**
   ```bash
   .venv/bin/python -I ml/entrenar.py                                         # -> ml/artefactos/ (3 archivos)
   .venv/bin/python -I scripts/exportar_catalogo.py --salida dist/catalogo    # -> dist/catalogo/ (2 archivos)
   ```
   En la consola, S3 → `utec-promptcorn-tools-datos`:
   - **Create folder** `modelo` → **Upload** `vectores.npy`, `catalogo_ml.json` y `meta.json`.
   - **Create folder** `catalogo` → **Upload** `catalogo.json` e `ids_externos.json`.

   Deben quedar en `modelo/vectores.npy` y `catalogo/catalogo.json`.

---

## Parte 1. EC2 de despliegue (una vez)

1. Learner Lab → **Start Lab** → **AWS**. Revisa que la región sea **us-east-1**.
2. EC2 → **Launch instance:**
   - Nombre `promptcorn-despliegue`.
   - **Amazon Linux 2023**, tipo **t3.small**. La t3.micro tiene poca memoria para npm.
   - Key pair `vockey`, o ninguno si te conectas con EC2 Instance Connect.
   - **Advanced details → IAM instance profile → `LabInstanceProfile`.** Así la EC2 tiene las credenciales del lab y no hay que copiar llaves de AWS.
   - Launch.
3. **Connect → EC2 Instance Connect → Connect.**
4. Instala las herramientas:
   ```bash
   sudo dnf install -y git zip python3-pip
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
   source ~/.bashrc && nvm install 22
   npm install -g serverless@4.46.0
   git clone https://github.com/shadow-maker/PromptCorn.git
   ```
5. **Inicia sesión en Serverless:** `serverless login`. Abre en tu navegador el link que aparece, entra con la cuenta de la org y vuelve a la terminal.
   - Alternativa: en app.serverless.com → **Settings → Access Keys**, crea una key y agrégala abajo como `export SERVERLESS_ACCESS_KEY='...'`.
6. **Secretos:** `nano ~/.promptcorn.env` con este contenido:
   ```bash
   export TMDB_TOKEN='...'      # en tu Mac: pbcopy < ~/.config/promptcorn/tmdb_token, y pegar aquí
   export GROQ_API_KEY='...'    # la key de Groq de B
   export GROQ_API_KEY_2='...'  # opcional: key de una segunda cuenta de Groq (se alternan por mensaje)
   ```
   Guarda con Ctrl+O, Enter y Ctrl+X. Luego: `chmod 600 ~/.promptcorn.env`
   - `desplegar.sh` carga este archivo solo. Para que también estén en cada terminal nueva (p. ej. para `serverless logs`):
     `echo '[ -f ~/.promptcorn.env ] && . ~/.promptcorn.env' >> ~/.bashrc`
   - El archivo vive en el disco de la EC2: sobrevive a reiniciar el lab, detener la instancia o cerrar la terminal. Solo se pierde si terminas (borras) la instancia. No uses `export` sueltos en la terminal: esos sí se pierden al cerrarla.

---

## Parte 2. Desplegar

```bash
cd PromptCorn
despliegue/desplegar.sh
```
El script hace todo esto:
1. `git pull`.
2. Empaqueta las 3 Lambdas con sus dependencias para Linux (y la layer de numpy la primera vez).
3. `serverless deploy`, que crea o actualiza el stack. La primera vez tarda unos 3–5 minutos.
4. Compila el frontend con la URL de la API, que toma sola del stack, y lo sube a `utec-promptcorn-chat-web`, junto con la documentación interactiva de la API en `/docs/`.

Al final muestra los endpoints de la API, la URL del sitio y la de la documentación (`<sitio>/docs/`, Swagger UI con **Try it out** contra la API real).

**Después de cada cambio en el repo:** `despliegue/desplegar.sh`. Solo se actualiza lo que cambió.

| Comando | Qué hace |
|---|---|
| `despliegue/desplegar.sh` | Todo: backend + frontend |
| `despliegue/desplegar.sh backend` | Solo Lambdas, API y tablas |
| `despliegue/desplegar.sh frontend` | Solo el sitio web |
| `serverless info` | Endpoints y recursos del stack |
| `serverless logs -f chat` (o `recomendar`, `herramientas`) | Logs de una Lambda |
| `CAPA=1 despliegue/desplegar.sh backend` | Rearma la layer de numpy (no hace falta normalmente) |

**Apaga la EC2 (Instance state → Stop) cuando termines,** para no gastar créditos. Si el lab se reinicia, enciéndela de nuevo: todo sigue ahí.

**Datos nuevos (modelo o catálogo):** súbelos como en la parte 0.3 y corre `despliegue/desplegar.sh backend` para que las Lambdas los vuelvan a cargar.

---

## Parte 3. Probar

**Por HTTP** (la URL sale al final del despliegue o con `serverless info`):
```bash
API=https://xxxx.execute-api.us-east-1.amazonaws.com
curl -s -X POST $API/recomendar -H 'Content-Type: application/json' -d '{"cantidad": 2, "guardar": false}'
curl -s -X POST $API/buscar_pelicula -H 'Content-Type: application/json' -d '{"titulo": "Interstellar"}'
curl -s -X POST $API/chat -H 'Content-Type: application/json' -d '{"usuario_id":"prueba","mensaje":"Recomiéndame una comedia corta"}'
```
- `recomendar`: 2 películas en `modo: arranque_en_frio`.
- `buscar_pelicula`: Interestelar (`id` 8318) primero.
- `chat`: `respuesta` con películas del catálogo.

**En la consola de Lambda (Test),** con los eventos de `tools/recomendar/eventos/` y `tools/herramientas/eventos/`. Hay una tabla de lo esperado más abajo.

**En el navegador**, con la URL del sitio, escribe esta conversación en orden:
1. "Tengo Netflix, Prime y HBO"
2. "Vi Interstellar y me encantó, le pongo 5"
3. "Recomiéndame algo" → debe salir el motivo "Interestelar"
4. "Dame otras opciones"
5. "Algo parecido a Toy Story"
6. "¿Dónde puedo ver Matrix?"
7. "¿Y Oppenheimer?" → debe explicar que no está en el catálogo
8. "¿Qué me recomendaste hoy?"

| Evento de consola | Esperado |
|---|---|
| recomendar `01_basico.json` | `modo: arranque_en_frio`, aviso de que no hay plataformas guardadas |
| herramientas `03_donde_ver.json` | `avisos: []`. Si trae un aviso, revisa `TMDB_TOKEN` |
| herramientas `04_guardar_plataformas.json` y `05_registrar_vista.json`, luego recomendar `01_basico.json` | `modo: perfil`, motivo "Interestelar" |

---

## Si algo falla
| Síntoma | Causa probable |
|---|---|
| `REEMPLAZAR_CON_TU_ORG` | Falta poner la org en `serverless.yml` (parte 0.1) |
| `falta TMDB_TOKEN / GROQ_API_KEY` | Falta `~/.promptcorn.env`, o no se cargó (parte 1.6) |
| El deploy pide login o falla con la licencia | `serverless login` otra vez, o `SERVERLESS_ACCESS_KEY` en `~/.promptcorn.env` |
| `Unable to locate credentials` o `AccessDenied` al desplegar | La EC2 no tiene `LabInstanceProfile`: **Actions → Security → Modify IAM role** |
| `... already exists` | Un recurso con ese nombre se creó a mano: bórralo (parte 0.2) y vuelve a desplegar |
| El stack queda en `ROLLBACK_COMPLETE` | CloudFormation → `promptcorn-prod` → **Events** muestra la causa. Borra el stack y vuelve a desplegar |
| Advertencia sobre el runtime `python3.14` | Si la versión de Serverless no lo tiene en su lista, solo advierte; el deploy sigue |
| Error 500 | `serverless logs -f <función>`, o CloudWatch. La línea `ERROR ...` dice qué pasó |
| `NoSuchKey` en los logs | Faltan archivos en `modelo/` o `catalogo/` de `utec-promptcorn-tools-datos` |
| `recomendar` siempre en `arranque_en_frio` | Todavía no hay notas en `promptcorn-tools-vistas` |
| El chat tarda más de 30 s o da 503 | Groq lento: `serverless logs -f chat` |
| `npm` falla | Node viejo: `nvm install 22` |
| Nada responde | La sesión del lab expiró. **Start Lab** de nuevo; los recursos se conservan |

`serverless remove` borra todo el stack, **incluidas las tablas con sus datos**. Úsalo solo para empezar de cero. No toca `utec-promptcorn-tools-datos`.
