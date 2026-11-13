# Despliegue manual en AWS Academy (Learner Lab)

Todo se hace desde la consola, en **us-east-1**, con el rol **`LabRole`** (Learner Lab no deja crear roles). Los agentes de IA no tocan AWS: esta guía es para el equipo.

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
1. S3 → **Create bucket**.
   - Nombre: `promptcorn-tools-modelo-<sufijo>`. Los nombres de bucket son únicos en todo AWS; usa por ejemplo tus iniciales y un número.
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
| `BUCKET_ARTEFACTOS` | `promptcorn-tools-modelo-<sufijo>` |
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

### Notas de Learner Lab
- Los recursos persisten entre sesiones, pero solo responden mientras el lab está iniciado.
- Si algo responde `AccessDenied`, revisa que la función use `LabRole`.
