# Modelo de ML de PromptCorn

Filtrado colaborativo **item-item** con SVD. Offline se aprende un vector por película a partir de las calificaciones; en línea, la Lambda `/recomendar` arma el perfil del usuario con sus notas y rankea el catálogo con numpy.

## Código

| Archivo | Qué hace |
|---|---|
| `ml/entrenar.py` | Filtra, centra, factoriza (SVD), evalúa la grilla de configuraciones y exporta los artefactos |
| `tools/recomendar/recomendador.py` | Núcleo puro (filtros, perfil, puntaje, motivo). Lo usan la Lambda **y** la evaluación: lo medido es lo que corre en producción |
| `tools/recomendar/handler.py` | Lambda `/recomendar`: carga el modelo de S3 y lee/escribe DynamoDB. Contrato en [contratos.md](contratos.md); despliegue en [despliegue.md](despliegue.md) |
| `tests/test_recomendar.py` | Pruebas del núcleo, del handler (almacén en memoria) y del modelo real |
| `ml/metricas.json` | Resultados de la evaluación (versionado, para el informe) |
| `ml/artefactos/` | `vectores.npy`, `catalogo_ml.json`, `meta.json`. No versionado; se sube a S3 |

```bash
.venv/bin/python -I ml/entrenar.py            # ~5 s
```

## Entrenamiento (offline)

1. **Películas del modelo:** las que tienen al menos 5 calificaciones (de los 610 usuarios del dataset). Con menos, el vector es ruido. Quedan **3,641 películas** (90 % de las calificaciones), de las cuales **1,892** están en alguna plataforma de Perú.
2. **Matriz usuario × película** centrada por la media de cada usuario; lo no calificado = 0.
3. **SVD truncado:** R ≈ U·Σ·Vᵀ. Vector de cada película = filas de V·Σ (k columnas), normalizado para similitud coseno.

## Recomendación (en línea)

- **Perfil** = Σ (nota − 3) · vector de cada película calificada. Un 5 suma, un 1 resta, un 3 no aporta. "No me interesa" resta como un 2. "Visto" sin nota solo se excluye.
- **Afinidad** = coseno(perfil, vector de la candidata).
- **Puntaje** = 0.5 · afinidad + 0.5 · popularidad (cuántos usuarios la calificaron, en escala log 0..1).
- **"Parecida a X":** el perfil es el vector de X; la afinidad pesa 0.8 para que lo popular no tape a lo parecido.
- **Arranque en frío** (sin notas): solo popularidad, dentro de los filtros.
- **Filtros duros** antes de rankear: géneros, duración máxima, rango de años, plataformas del usuario y exclusiones (vistas, descartadas, recomendadas en el último día).
- **Motivo:** la película calificada que más aporta al puntaje ("porque le diste 5 a Interestelar").

## Evaluación

Split **temporal por usuario**: el 20 % más reciente de cada usuario se esconde. Se entrena con el resto y se mide si el top-10 (sin repetir lo ya visto) recupera lo que el usuario calificó luego con ≥ 4. 602 usuarios evaluados.

| Modelo | HitRate@10 | Recall@10 |
|---|---|---|
| Baseline: lo más visto | 0.485 | 0.125 |
| Baseline: mejor puntuado (promedio bayesiano) | 0.394 | 0.091 |
| SVD solo afinidad (k=64) | 0.455 | 0.117 |
| **SVD k=64 + popularidad (0.5 / 0.5)** | **0.591** | **0.182** |

- HitRate@10: fracción de usuarios con al menos un acierto en su top-10.
- Recall@10: aciertos / mín(10, n.º de relevantes), promediado por usuario.
- El modelo elegido supera al baseline más fuerte en **+46 % de Recall@10**. Se probó k ∈ {16, 32, 64, 128}, peso ∈ {1.0, 0.7, 0.5, 0.3} y dos priors (popularidad, calidad). Tabla completa en `ml/metricas.json`.

Hallazgos que justifican el diseño:
- **Solo afinidad no basta.** "Lo más visto" es un baseline muy fuerte en MovieLens, porque la gente califica lo que vio y ve lo popular. Mezclar afinidad con popularidad le gana a ambos por separado.
- **Popularidad > calidad como prior.** La calidad (puntaje bayesiano) rinde peor offline.
- **Centrar en 3 > centrar en la media del usuario** para el perfil en línea: 0.182 vs 0.157 de Recall@10. Con pocas notas, la media del usuario es inestable, y 3 es la mitad natural de la escala.
- **Con k=64** se explica el 55 % de la varianza. Con k=128 no mejora (0.178).

Limitaciones (para el informe):
- La configuración se eligió sobre el mismo split que se reporta: no hubo validación aparte.
- El catálogo llega hasta 2018.
- La disponibilidad por plataforma es un snapshot.
- El modo "parecida a X" no tiene métrica offline; su peso se ajustó revisando ejemplos.

## Artefactos y despliegue

| Artefacto | Contenido | Tamaño |
|---|---|---|
| `vectores.npy` | 3,641 × 64 float32, fila i ↔ `catalogo_ml[i]` | ~0.9 MB |
| `catalogo_ml.json` | id, título, año, duración, géneros, plataformas, sinopsis corta, póster, popularidad, calidad | ~1.8 MB |
| `meta.json` | k, prior, peso, umbral, fecha, conteos | — |

Van a **S3** (decidido). La Lambda los carga al arrancar y los mantiene en memoria. Reentrenar = correr el script y volver a subir los tres archivos, sin redesplegar la Lambda.
