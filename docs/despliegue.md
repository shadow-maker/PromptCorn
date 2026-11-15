# Despliegue en AWS Academy (Learner Lab)

Región **us-east-1**, rol **`LabRole`** (Learner Lab no deja crear roles) y runtime **Python 3.14** en todas las Lambdas. La consola ofrece 3.15, pero los binarios (numpy, pydantic-core) están armados para 3.14 y no cargan en otra versión.

Los agentes de IA no tocan AWS: esta guía es para el equipo.

## Cómo funciona

```
GitHub (repo) ──git pull──► CloudShell o EC2 de despliegue ──despliegue/actualizar.sh──► Lambdas, layer, S3 web
Tu máquina (datos locales) ──modelo y catálogo──────────────────────────────────────────► S3 (utec-promptcorn-tools-datos)
```

- **Una sola vez, en la consola:** se crean los recursos vacíos (buckets, tablas, Lambdas, APIs) y se cargan los secretos en las variables de entorno.
- **En cada cambio:** en la máquina de despliegue se corre `despliegue/actualizar.sh`. El script hace `git pull`, empaqueta y actualiza las Lambdas. No se sube ningún zip a mano.
- **El modelo y el catálogo** se suben desde tu máquina, porque los datos no están en el repo por la licencia. Casi nunca cambian.
- **Los secretos** (token de la API de metadatos y key de Groq) van en las variables de entorno de cada Lambda, que Lambda guarda cifradas. Learner Lab no da acceso a SSM Parameter Store; en producción irían ahí o en Secrets Manager. El script nunca toca las variables de entorno.
- **La configuración que no es secreta** (nombres de buckets y Lambdas, URL del chat) está en `despliegue/config.sh`.

---

## Parte 1. Crear los recursos (una vez, en la consola)

### 1.1 S3
- **`utec-promptcorn-tools-datos`** (ya existe): **Block all public access** activado. Las carpetas `modelo/` y `catalogo/` se llenan en la parte 3.
- **`utec-promptcorn-chat-web`** (frontend):
  1. **Create bucket** y desmarca **Block all public access**.
  2. **Properties → Static website hosting → Enable**, con index document `index.html`.
  3. **Permissions → Bucket policy:**
     ```json
     {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
       "Resource": "arn:aws:s3:::utec-promptcorn-chat-web/*"}]}
     ```

### 1.2 DynamoDB (4 tablas, **Capacity mode: On-demand**)

| Tabla | Partition key | Sort key |
|---|---|---|
| `promptcorn-tools-vistas` | `usuario_id` (String) | `pelicula_id` (**Number**) |
| `promptcorn-tools-perfil` | `usuario_id` (String) | — |
| `promptcorn-tools-recomendaciones` | `usuario_id` (String) | `sk` (String) |
| `promptcorn-chat-conversaciones` | `usuario_id` (String) | `mensaje_id` (String) |

El tipo se elige en el desplegable al lado de cada key. Para verificarlo: Tables → `promptcorn-tools-vistas` → **Overview** debe decir `pelicula_id (Number)`. Si quedó como String, borra la tabla y créala de nuevo.

### 1.3 Lambdas (vacías: el código lo sube el script)
Lambda → **Create function → Author from scratch**, tres veces, todas con Runtime **Python 3.14**, Architecture **x86_64** y **Use an existing role → `LabRole`**. No subas código ni cambies el handler: el script fija handler, memoria y timeout.

Después, en **Configuration → Environment variables** de cada una:

**`promptcorn-tools-recomendar`**

| Key | Value |
|---|---|
| `BUCKET_ARTEFACTOS` | `utec-promptcorn-tools-datos` |
| `PREFIJO_ARTEFACTOS` | `modelo/` |
| `TABLA_VISTAS` | `promptcorn-tools-vistas` |
| `TABLA_PERFIL` | `promptcorn-tools-perfil` |
| `TABLA_RECOMENDACIONES` | `promptcorn-tools-recomendaciones` |
| `USUARIO_ID` | `usuario-demo` |

**`promptcorn-tools-herramientas`**

| Key | Value |
|---|---|
| `BUCKET_CATALOGO` | `utec-promptcorn-tools-datos` |
| `PREFIJO_CATALOGO` | `catalogo/` |
| `TMDB_TOKEN` | El token. Cópialo sin mostrarlo con `pbcopy < ~/.config/promptcorn/tmdb_token` |
| `TABLA_VISTAS` | `promptcorn-tools-vistas` |
| `TABLA_PERFIL` | `promptcorn-tools-perfil` |
| `TABLA_RECOMENDACIONES` | `promptcorn-tools-recomendaciones` |
| `USUARIO_ID` | `usuario-demo` |

**`promptcorn-chat`**

| Key | Value |
|---|---|
| `CONVERSATIONS_TABLE` | `promptcorn-chat-conversaciones` |
| `GROQ_API_KEY` | La key de Groq |
| `GROQ_MODEL` | `openai/gpt-oss-20b` |
| `MOCK_MODE` | `false` |
| `API_TOOLS_URL` | Invoke URL de `promptcorn-tools-api` (paso 1.4), sin `/` al final |

### 1.4 API Gateway (2 HTTP APIs)
1. **`promptcorn-tools-api`:** Create API → HTTP API → Build.
   - Integrations: Lambda `promptcorn-tools-recomendar` y Lambda `promptcorn-tools-herramientas`.
   - Routes:
     - `POST /recomendar` → recomendar.
     - `POST /{herramienta}` → herramientas. Una sola ruta cubre las 5 herramientas.
   - Stage `$default` con auto-deploy.
   - Copia la Invoke URL en `API_TOOLS_URL` de `promptcorn-chat`.
2. **`promptcorn-chat-api`:**
   - Integration: Lambda `promptcorn-chat`.
   - Route: `POST /chat`.
   - Stage `$default` con auto-deploy.
   - **CORS:** origin `*`, methods `POST, OPTIONS`, headers `content-type`.
   - Pon la Invoke URL + `/chat` en `CHAT_API_URL` de `despliegue/config.sh`, y haz commit y push. Esta URL es pública; no es un secreto.

---

## Parte 2. Preparar la máquina de despliegue (una vez)

### Opción A: AWS CloudShell (recomendada)
1. En la consola, ícono **`>_`** (barra superior), en us-east-1.
2. Clona el repo:
   ```bash
   git clone https://github.com/shadow-maker/PromptCorn.git
   ```
El home de CloudShell persiste entre sesiones: el repo queda clonado para la próxima vez.

### Opción B: EC2 (si CloudShell no está disponible)
1. EC2 → **Launch instance:**
   - Nombre `promptcorn-despliegue`.
   - **Amazon Linux 2023**, tipo **t3.micro**.
   - Key pair `vockey`, o ninguno si te conectas con EC2 Instance Connect.
   - En **Advanced details → IAM instance profile** elige **`LabInstanceProfile`**. Así la instancia tiene las credenciales del lab sin copiar llaves.
2. **Connect → EC2 Instance Connect**, y luego:
   ```bash
   sudo dnf install -y git zip python3-pip
   git clone https://github.com/shadow-maker/PromptCorn.git
   ```
3. **Detén la instancia (Stop) cuando no estés desplegando,** para no gastar créditos del lab.

Esta EC2 solo se usa para desplegar. La app sigue siendo 100 % serverless, así que no va en el diagrama de arquitectura.

### Node (solo para desplegar el frontend)
Vite necesita Node 20.19 o superior. Comprueba con `node -v`. Si falta o es más viejo:
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && source ~/.bashrc && nvm install 22
```

---

## Parte 3. Modelo y catálogo a S3 (desde tu máquina)
Los datos no están en el repo, así que esto sale de tu máquina:
```bash
.venv/bin/python -I ml/entrenar.py            # -> ml/artefactos/
tools/recomendar/empaquetar.sh                # -> dist/modelo/
tools/herramientas/empaquetar.sh              # -> dist/catalogo/
```
En la consola, bucket `utec-promptcorn-tools-datos`:
- **Create folder** `modelo` → **Upload** los 3 archivos de `dist/modelo/`.
- **Create folder** `catalogo` → **Upload** los 2 archivos de `dist/catalogo/`.

Deben quedar en `modelo/vectores.npy` y `catalogo/catalogo.json`, no en una subcarpeta extra.

Alternativa: si configuras en tu máquina la AWS CLI con las credenciales del lab (Learner Lab → **AWS Details → AWS CLI → Show**, copiadas en `~/.aws/credentials`; vencen con la sesión), puedes usar `despliegue/actualizar.sh modelo catalogo`.

---

## Parte 4. Desplegar el código

En la máquina de despliegue:
```bash
cd PromptCorn
despliegue/actualizar.sh todo     # la primera vez: layer de numpy + 3 Lambdas + frontend
```
**Después de cada cambio en el repo:**
```bash
cd PromptCorn
despliegue/actualizar.sh          # git pull + las 3 Lambdas (~1 min)
despliegue/actualizar.sh chat     # o solo lo que cambió: recomendar, herramientas, chat, frontend
```

| Componente | Qué hace |
|---|---|
| `recomendar`, `herramientas`, `chat` | Empaqueta la carpeta, sube el código y fija runtime, handler, memoria y timeout |
| `frontend` | Compila con `CHAT_API_URL` y sincroniza `utec-promptcorn-chat-web` |
| `capa` | Publica una versión nueva de la layer de numpy y la conecta a `recomendar`. Solo hace falta la primera vez |
| `modelo`, `catalogo` | Suben los datos a S3. Solo funcionan donde están los datos (tu máquina) |
| `todo` | Todo lo anterior que se pueda en esa máquina |

`DRY_RUN=1 despliegue/actualizar.sh todo` muestra los comandos sin ejecutarlos.

---

## Parte 5. Probar

**En la consola de cada Lambda (Test),** con los eventos del repo:

| Lambda | Evento | Esperado |
|---|---|---|
| recomendar | `tools/recomendar/eventos/01_basico.json` | `modo: arranque_en_frio` y un aviso de que no hay plataformas guardadas |
| herramientas | `tools/herramientas/eventos/01_buscar.json` | Interestelar (`id` 8318) primero |
| herramientas | `03_donde_ver.json` | `avisos: []`. Si trae un aviso, revisa `TMDB_TOKEN` |
| herramientas | `04_guardar_plataformas.json` y `05_registrar_vista.json` | `ok: true` |
| recomendar | `01_basico.json` otra vez | Ahora `modo: perfil`, motivo "Interestelar", solo en Netflix, Prime Video o HBO Max |
| chat | `{"body": "{\"usuario_id\": \"prueba\", \"mensaje\": \"Recomiéndame una comedia corta\"}"}` | `statusCode: 200` con películas del catálogo |

**Por HTTP:**
```bash
API=<invoke-url de promptcorn-tools-api>
curl -s -X POST $API/recomendar -H 'Content-Type: application/json' -d '{"cantidad": 2, "guardar": false}'
curl -s -X POST $API/buscar_pelicula -H 'Content-Type: application/json' -d '{"titulo": "Matrix"}'
curl -s -X POST <invoke-url de promptcorn-chat-api>/chat -H 'Content-Type: application/json' -d '{"usuario_id":"prueba","mensaje":"hola"}'
```

**En el navegador** (URL de Static website hosting de `utec-promptcorn-chat-web`), escribe esta conversación en orden:
1. "Tengo Netflix, Prime y HBO"
2. "Vi Interstellar y me encantó, le pongo 5"
3. "Recomiéndame algo" → debe salir el motivo "Interestelar"
4. "Dame otras opciones"
5. "Algo parecido a Toy Story"
6. "¿Dónde puedo ver Matrix?"
7. "¿Y Oppenheimer?" → debe explicar que no está en el catálogo
8. "¿Qué me recomendaste hoy?"

---

## Si algo falla
| Síntoma | Causa probable |
|---|---|
| `AccessDenied` (Lambda) | La función no usa `LabRole` |
| `AccessDenied` (script en EC2) | La instancia no tiene `LabInstanceProfile`: **Actions → Security → Modify IAM role** |
| `ResourceNotFoundException` (script) | El nombre de la Lambda o del bucket no coincide con `despliegue/config.sh` |
| `Runtime.ImportModuleError` | La Lambda no está en Python 3.14, o falta la layer (corre `actualizar.sh capa`) |
| Error 500 | Lambda → **Monitor → View CloudWatch logs**. La línea `ERROR ...` dice qué pasó |
| `NoSuchKey` en los logs | Faltan archivos en `modelo/` o `catalogo/` del bucket |
| `recomendar` siempre en `arranque_en_frio` | `pelicula_id` quedó como String, o `USUARIO_ID` es distinto entre las Lambdas |
| `ver_donde_ver` siempre con aviso | Falta `TMDB_TOKEN` o está mal copiado |
| El chat tarda más de 30 s o da 503 | Groq lento: revisa los logs de `promptcorn-chat` |
| El navegador muestra un error de CORS | Falta la configuración de CORS en `promptcorn-chat-api` |
| `npm` falla al desplegar el frontend | Node viejo: ver "Node" en la parte 2 |
| La primera llamada es lenta (1–3 s) | Es normal: carga el modelo y el catálogo |
| Nada responde | La sesión del lab expiró. **Start Lab** de nuevo; los recursos se conservan |
