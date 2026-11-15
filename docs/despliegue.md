# Despliegue manual en AWS Academy (Learner Lab)

Todo se hace desde la consola, en **us-east-1**, con el rol **`LabRole`** (Learner Lab no deja crear roles).

**Secretos (token de la API de metadatos y key de Groq):** van en las **variables de entorno de cada Lambda** (Configuration → Environment variables). Lambda las guarda cifradas. Learner Lab no da acceso a SSM Parameter Store; en producción irían ahí o en Secrets Manager. El código soporta ambas opciones: `*_PARAM` para SSM, o la variable directa. Nunca en el repo.

**Runtime de todas las Lambdas: Python 3.14.** La consola ofrece 3.15, pero los binarios incluidos (numpy, pydantic-core) son para 3.14 y no cargan en otra versión.

Los agentes de IA no tocan AWS: esta guía es para el equipo.

## `recomendar` (API del modelo de ML)

### 0. Preparar los archivos (local)

```bash
uv sync
.venv/bin/python -I ml/entrenar.py               # entrena y evalúa (~5 s) -> ml/artefactos/
.venv/bin/python -I -m unittest discover -s tests # pruebas (deben pasar todas)
tools/recomendar/empaquetar.sh                    # arma dist/
```

| Archivo en `dist/` | Va a |
|---|---|
| `modelo/vectores.npy`, `modelo/catalogo_ml.json`, `modelo/meta.json` | S3 |
| `capa-numpy-python3.14.zip` (o `3.13`) | Layer de Lambda |
| `promptcorn-tools-recomendar.zip` | Código de la Lambda |

### 1. S3: artefactos del modelo
Un solo bucket para los datos del backend: `modelo/` (este paso) y `catalogo/` (Lambda de herramientas).
1. S3 → **Create bucket**.
   - Nombre: `utec-promptcorn-tools-datos`. Los nombres de bucket son únicos en todo AWS.
   - Región us-east-1.
   - Deja activado **Block all public access**.
2. Entra al bucket → **Create folder** `modelo`.
3. Dentro de `modelo/` → **Upload** los 3 archivos de `dist/modelo/`.

### 2. DynamoDB: tablas
DynamoDB → **Create table**, una vez por cada tabla, con **Table settings: Customize → Capacity mode: On-demand**:

| Nombre | Partition key | Sort key |
|---|---|---|
| `promptcorn-tools-vistas` | `usuario_id` (String) | `pelicula_id` (Number) |
| `promptcorn-tools-perfil` | `usuario_id` (String) | — |
| `promptcorn-tools-recomendaciones` | `usuario_id` (String) | `sk` (String) |

### 3. Layer con numpy
Lambda → **Layers** → **Create layer**:
- Nombre `promptcorn-tools-numpy`.
- Upload `dist/capa-numpy-python3.14.zip`. Si la consola no ofrece Python 3.14, usa el de `3.13`.
- Compatible architectures: **x86_64**.
- Compatible runtimes: la misma versión de Python.

### 4. Función Lambda
1. Lambda → **Create function** → Author from scratch:
   - Nombre `promptcorn-tools-recomendar`.
   - Runtime **Python 3.14** (o 3.13, igual que la layer).
   - Architecture **x86_64**.
   - **Change default execution role → Use an existing role → `LabRole`**.
2. **Code → Upload from → .zip file** → `dist/promptcorn-tools-recomendar.zip`.
3. **Runtime settings → Edit → Handler:** `handler.lambda_handler`.
4. **Layers → Add a layer → Custom layers** → `promptcorn-tools-numpy`, última versión.
5. **Configuration → General configuration → Edit:** Memory **512 MB**, Timeout **15 s**.
6. **Configuration → Environment variables:**

| Variable | Valor |
|---|---|
| `BUCKET_ARTEFACTOS` | `utec-promptcorn-tools-datos` |
| `PREFIJO_ARTEFACTOS` | `modelo/` |
| `TABLA_VISTAS` | `promptcorn-tools-vistas` |
| `TABLA_PERFIL` | `promptcorn-tools-perfil` |
| `TABLA_RECOMENDACIONES` | `promptcorn-tools-recomendaciones` |
| `USUARIO_ID` | `usuario-demo` |

### 5. Probar en la consola
**Test** → crea un evento con el contenido de cada archivo de `tools/recomendar/eventos/`:

| Evento | Esperado |
|---|---|
| `01_basico.json` | `modo: arranque_en_frio` (las tablas están vacías) y un aviso de que no hay plataformas guardadas |
| `02_con_filtros.json` | Comedias o animadas de ≤ 110 min, de 1995 en adelante |
| `03_parecido_a_toy_story.json` | `modo: parecido`, con Toy Story 2 entre las primeras (en Disney+) |
| `04_via_api_gateway.json` | `statusCode: 200` y el JSON dentro de `body` |
| `05_error_genero.json` | `error` con la lista `generos_validos` |

La primera invocación tarda ~1–2 s porque carga el modelo de S3. Las siguientes, milisegundos.

**Para probar el modo perfil:** DynamoDB → `promptcorn-tools-vistas` → **Explore table items → Create item → JSON view** (desactiva "View DynamoDB JSON"):
```json
{"usuario_id": "usuario-demo", "pelicula_id": 8318, "estado": "visto", "calificacion": 5, "fecha": "2026-11-15T20:00:00Z"}
```
(8318 = Interestelar). Vuelve a correr `01_basico.json`: ahora `modo: perfil` y `motivo: Interestelar`. Cada prueba con `guardar` en `true` escribe en `promptcorn-tools-recomendaciones`, y esas películas no se repiten por 24 h. Para probar varias veces lo mismo, agrega `"guardar": false` o borra esos ítems.

### 6. API Gateway
1. API Gateway → **Create API → HTTP API → Build**.
   - Integrations: **Lambda** → `promptcorn-tools-recomendar`.
   - API name `promptcorn-tools-api`. Las demás herramientas se agregan como rutas de esta misma API.
2. Route: **POST** `/recomendar` → la integración anterior.
3. Stage `$default` con **Auto-deploy**.
4. Copia la **Invoke URL** y prueba:
```bash
curl -s -X POST "<invoke-url>/recomendar" -H 'Content-Type: application/json' -d '{"cantidad": 2, "generos": ["Terror"]}'
```
Esa URL (+ `/recomendar`) es la que la Persona B pone en la variable de entorno del chat.

### Reentrenar o actualizar
- **Nuevo modelo:** corre `ml/entrenar.py` y `empaquetar.sh`, y vuelve a subir los 3 archivos a `modelo/`. Las instancias de Lambda que ya están corriendo guardan el modelo anterior en memoria. Para forzar la recarga, cambia cualquier variable de entorno (por ejemplo, agrega `VERSION_MODELO` con la fecha).
- **Nuevo código:** corre `empaquetar.sh` y sube de nuevo `promptcorn-tools-recomendar.zip` (Code → Upload from).

## Herramientas (`buscar_pelicula`, `ver_donde_ver`, `registrar_vista`, `guardar_plataformas`, `obtener_historial`)

Una sola Lambda para las 5 herramientas. Usa las mismas tablas y el mismo bucket que `recomendar`. No necesita layer, porque solo usa la librería estándar y boto3, que ya viene en el runtime.

### 0. Preparar (local)
```bash
tools/herramientas/empaquetar.sh   # -> dist/promptcorn-tools-herramientas.zip y dist/catalogo/
```

### 1. Catálogo en S3
En el bucket `utec-promptcorn-tools-datos`: **Create folder** `catalogo` → **Upload** `catalogo.json` e `ids_externos.json` de `dist/catalogo/`.

### 2. Función Lambda
1. **Create function:**
   - Nombre `promptcorn-tools-herramientas`.
   - Runtime Python 3.14 (o 3.13).
   - Arquitectura x86_64.
   - Rol **`LabRole`**.
2. **Upload from .zip** → `dist/promptcorn-tools-herramientas.zip`. Handler: `handler.lambda_handler`.
3. **General configuration:** Memory **256 MB**, Timeout **15 s**.
4. **Environment variables:**

| Variable | Valor |
|---|---|
| `BUCKET_CATALOGO` | `utec-promptcorn-tools-datos` |
| `PREFIJO_CATALOGO` | `catalogo/` |
| `TMDB_TOKEN` | El token de lectura (contenido de `~/.config/promptcorn/tmdb_token`) |
| `TABLA_VISTAS` | `promptcorn-tools-vistas` |
| `TABLA_PERFIL` | `promptcorn-tools-perfil` |
| `TABLA_RECOMENDACIONES` | `promptcorn-tools-recomendaciones` |
| `USUARIO_ID` | `usuario-demo` (el mismo que en `recomendar`) |

### 3. Probar en la consola
**Test** con cada archivo de `tools/herramientas/eventos/`:

| Evento | Esperado |
|---|---|
| `01_buscar.json` | Interestelar (`id` 8318, `en_catalogo: true`) primero |
| `02_buscar_fuera_de_catalogo.json` | Oppenheimer con `id: null`, `en_catalogo: false` |
| `03_donde_ver.json` | Plataformas de hoy y `avisos: []`. Si trae un aviso, la API externa no respondió: revisa la variable `TMDB_TOKEN` |
| `04_guardar_plataformas.json` | `["Netflix", "Prime Video", "HBO Max"]` |
| `05_registrar_vista.json` | `ok: true`, nota 5. Después, `recomendar` pasa a `modo: perfil` |
| `06_historial.json` | La vista registrada y lo que haya recomendado `recomendar` |
| `07_via_api_gateway.json` | `statusCode: 200` (Toy Story como `no_me_interesa`) |

### 4. Rutas en la API
En `promptcorn-tools-api` → **Routes → Create**: **POST** `/{herramienta}` → integración Lambda `promptcorn-tools-herramientas`. Con una sola ruta alcanzan las 5 herramientas. `POST /recomendar` es más específica y sigue yendo a su Lambda.

```bash
curl -s -X POST "<invoke-url>/buscar_pelicula" -H 'Content-Type: application/json' -d '{"titulo": "Interstellar"}'
```

### Notas de Learner Lab
- Los recursos persisten entre sesiones, pero solo responden mientras el lab está iniciado.
- Si algo responde `AccessDenied`, revisa que la función use `LabRole`.
- Las Lambdas sin VPC tienen salida a internet: `buscar_pelicula` y `ver_donde_ver` consultan la API externa directamente.

## Chat (Persona B)

### 0. Preparar (local)
```bash
chat/empaquetar.sh        # -> dist/promptcorn-chat-python3.14.zip (y 3.13)
```

### 1. Tabla de memoria
DynamoDB → **Create table** con nombre `promptcorn-chat-conversaciones`, partition key `usuario_id` (String), sort key `mensaje_id` (String) y capacidad On-demand.

### 2. Función Lambda
1. **Create function:**
   - Nombre `promptcorn-chat`.
   - Runtime Python 3.14 (o 3.13, igual que el zip).
   - Arquitectura x86_64.
   - Rol **`LabRole`**.
2. **Upload from .zip** → `dist/promptcorn-chat-python3.14.zip`.
   - Handler: `lambda_function.lambda_handler`. Es el valor por defecto.
3. **General configuration:** Memory 256 MB, Timeout **29 s**. API Gateway corta a los 30 s.
4. **Environment variables:**

| Variable | Valor |
|---|---|
| `CONVERSATIONS_TABLE` | `promptcorn-chat-conversaciones` |
| `GROQ_API_KEY` | La key de Groq |
| `GROQ_MODEL` | `openai/gpt-oss-20b` (o el que se elija) |
| `MOCK_MODE` | `false` (`true` = herramientas simuladas, sin backend) |
| `API_TOOLS_URL` | Invoke URL de `promptcorn-tools-api`, sin `/` al final |

5. **Test** con el evento:
```json
{"body": "{\"usuario_id\": \"prueba\", \"mensaje\": \"Recomiéndame una comedia corta\"}"}
```

### 3. API del chat
API Gateway → **Create API → HTTP API**:
- Integración Lambda `promptcorn-chat`.
- Nombre `promptcorn-chat-api`.
- Ruta **POST** `/chat`.
- Stage `$default` con auto-deploy.
- **CORS:** Allow origin `*`, Allow methods `POST, OPTIONS`, Allow headers `content-type`.

La URL `<invoke-url>/chat` es la que va en `VITE_API_URL` del frontend.

## Frontend (Persona B)
```bash
cd frontend && npm install
echo "VITE_API_URL=<invoke-url>/chat" > .env
npm run build             # -> frontend/dist/
```
1. S3 → **Create bucket** `promptcorn-chat-web-<sufijo>`. Desactiva **Block all public access** y acepta la advertencia.
2. **Properties → Static website hosting → Enable**, con index document `index.html`.
3. **Permissions → Bucket policy:** lectura pública de `arn:aws:s3:::promptcorn-chat-web-<sufijo>/*` (`s3:GetObject`, Principal `*`).
4. **Upload:** el *contenido* de `frontend/dist/`, no la carpeta.
5. La URL del sitio aparece en Static website hosting. CloudFront delante es opcional: da HTTPS y suma al diagrama.
