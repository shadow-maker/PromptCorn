"""Entrena el modelo de PromptCorn (SVD item-item), lo evalúa y exporta los artefactos.

1. Evaluación: por cada usuario, su 20 % de calificaciones más recientes se esconde (test).
   Se entrena con el resto y se mide si el top-10 recupera lo que luego calificó con >= 4.
   Se compara contra dos baselines (lo más visto y lo mejor puntuado) y se eligen k, el prior
   (popularidad o calidad) y su peso frente a la afinidad.
2. Entrenamiento final con todas las calificaciones y la configuración elegida.

Entradas:  data/processed/{peliculas,calificaciones}.parquet
Salidas:   ml/artefactos/vectores.npy, catalogo_ml.json, meta.json   (no versionados; van a S3)
           ml/metricas.json                                          (versionado; para el informe)

Uso: .venv/bin/python -I ml/entrenar.py [--min-notas 5]
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools" / "recomendar"))
from recomendador import Recomendador  # noqa: E402

DATOS = RAIZ / "data" / "processed"
ARTEFACTOS = RAIZ / "ml" / "artefactos"

KS = (16, 32, 64, 128)
PESOS = (1.0, 0.7, 0.5, 0.3)
PRIORS = ("popularidad", "calidad")
TOP = 10
FRACCION_TEST = 0.2
RELEVANTE = 4.0
SEMILLA = 42


# ---------- modelo ----------

def factorizar(cal: pd.DataFrame, ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """SVD de la matriz usuario x película centrada por usuario. Devuelve (V, s) completos."""
    col = {pid: j for j, pid in enumerate(ids)}
    usuarios = {u: i for i, u in enumerate(cal.usuario_id.unique())}
    R = np.zeros((len(usuarios), len(ids)), dtype=np.float64)
    centrada = cal.calificacion - cal.groupby("usuario_id").calificacion.transform("mean")
    R[cal.usuario_id.map(usuarios), cal.pelicula_id.map(col)] = centrada
    _, s, Vt = np.linalg.svd(R, full_matrices=False)
    return Vt.T, s


def vectores(V: np.ndarray, s: np.ndarray, k: int) -> np.ndarray:
    """Vector de cada película = V·Σ truncado a k, normalizado (para similitud coseno)."""
    X = V[:, :k] * s[:k]
    normas = np.linalg.norm(X, axis=1, keepdims=True)
    return (X / np.where(normas == 0, 1, normas)).astype(np.float32)


def calidad(pel: pd.DataFrame) -> np.ndarray:
    """Promedio bayesiano del puntaje (0..10), reescalado a 0..1. Pocas votaciones -> se acerca a la media."""
    R = pel.puntaje.astype(float)
    v = pel.votos.astype(float)
    C = R.mean()
    m = v.median()
    bayes = (v * R.fillna(C) + m * C) / (v + m)
    return ((bayes - bayes.min()) / (bayes.max() - bayes.min())).to_numpy()


def popularidad(pel: pd.DataFrame, cal: pd.DataFrame) -> np.ndarray:
    """Cuántos usuarios la calificaron, en escala log, reescalado a 0..1."""
    n = np.log1p(cal.pelicula_id.value_counts().reindex(pel.id, fill_value=0).to_numpy(dtype=float))
    return n / n.max()


def resumir(texto, maximo: int = 300) -> str | None:
    """Sinopsis corta para la respuesta de la API (corta en la última palabra completa)."""
    if not isinstance(texto, str) or not texto:
        return None
    return texto if len(texto) <= maximo else texto[:maximo].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def catalogo_ml(pel: pd.DataFrame, cal: pd.DataFrame) -> list[dict]:
    """Catálogo del modelo: solo lo que la Lambda necesita para filtrar, rankear y responder."""
    return [
        {"id": int(r.id), "titulo": r.titulo, "anio": None if pd.isna(r.anio) else int(r.anio),
         "duracion_min": None if pd.isna(r.duracion_min) else int(r.duracion_min),
         "generos": list(r.generos), "plataformas": list(r.plataformas),
         "sinopsis": resumir(r.sinopsis), "poster": r.poster if isinstance(r.poster, str) else None,
         "popularidad": round(float(pop), 4), "calidad": round(float(q), 4)}
        for r, pop, q in zip(pel.itertuples(), popularidad(pel, cal), calidad(pel))
    ]


def peliculas_del_modelo(cal: pd.DataFrame, pel: pd.DataFrame, min_notas: int) -> pd.DataFrame:
    n = cal.pelicula_id.value_counts()
    ids = n[n >= min_notas].index
    return pel[pel.id.isin(ids)].sort_values("id").reset_index(drop=True)


# ---------- evaluación ----------

def dividir(cal: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Por usuario: el 20 % más reciente a test (empates de fecha se rompen al azar con semilla fija)."""
    cal = cal.assign(_azar=np.random.default_rng(SEMILLA).random(len(cal)))
    cal = cal.sort_values(["usuario_id", "fecha", "_azar"])
    pos = cal.groupby("usuario_id").cumcount()
    n = cal.groupby("usuario_id").calificacion.transform("size")
    es_test = pos >= np.ceil(n * (1 - FRACCION_TEST))
    return cal[~es_test].drop(columns="_azar"), cal[es_test].drop(columns="_azar")


def evaluar(ranking, train: pd.DataFrame, test: pd.DataFrame, fila: dict[int, int]) -> dict:
    """HitRate@10 y Recall@10. ranking(notas) -> puntaje por fila del catálogo."""
    vistas = train.groupby("usuario_id")
    relevantes = test[test.calificacion >= RELEVANTE].groupby("usuario_id").pelicula_id.apply(
        lambda s: {fila[p] for p in s if p in fila})
    aciertos, recall, usuarios = 0, 0.0, 0
    for u, rel in relevantes.items():
        if not rel:
            continue
        g = vistas.get_group(u)
        notas = dict(zip(g.pelicula_id, g.calificacion))
        puntaje = ranking(notas).astype(np.float64)
        puntaje[[fila[p] for p in notas if p in fila]] = -np.inf  # no recomendar lo ya visto
        top = set(np.argpartition(-puntaje, TOP)[:TOP])
        h = len(top & rel)
        aciertos += h > 0
        recall += h / min(TOP, len(rel))
        usuarios += 1
    return {"hit_rate@10": round(aciertos / usuarios, 4), "recall@10": round(recall / usuarios, 4), "usuarios": usuarios}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-notas", type=int, default=5, help="calificaciones mínimas para entrar al modelo")
    args = ap.parse_args()

    pel = pd.read_parquet(DATOS / "peliculas.parquet")
    cal = pd.read_parquet(DATOS / "calificaciones.parquet")

    # 1. Evaluación (todo calculado solo con train)
    train, test = dividir(cal)
    pel_ev = peliculas_del_modelo(train, pel, args.min_notas)
    ids_ev = pel_ev.id.to_numpy()
    train_ev = train[train.pelicula_id.isin(ids_ev)]
    V, s = factorizar(train_ev, ids_ev)
    cat_ev = catalogo_ml(pel_ev, train_ev)
    fila = {pid: i for i, pid in enumerate(ids_ev)}

    resultados = {}
    for prior in PRIORS:
        base = np.array([p[prior] for p in cat_ev])
        resultados[f"baseline_{prior}"] = evaluar(lambda _: base.copy(), train, test, fila)
    for k in KS:
        X = vectores(V, s, k)
        for prior in PRIORS:
            for w in PESOS:
                rec = Recomendador(X, cat_ev, peso_afinidad=w, prior=prior)
                resultados[f"svd_k{k}_{prior}_w{w}"] = {
                    "k": k, "prior": prior, "peso_afinidad": w,
                    **evaluar(lambda notas: rec.puntajes(rec.pesos_perfil(notas))[1], train, test, fila)}
    print(f"{'modelo':<34}{'hit@10':>8}{'recall@10':>11}")
    for nombre, r in resultados.items():
        print(f"{nombre:<34}{r['hit_rate@10']:>8.3f}{r['recall@10']:>11.3f}")

    mejor = max((r for n, r in resultados.items() if n.startswith("svd")), key=lambda r: r["recall@10"])
    k, prior, w = mejor["k"], mejor["prior"], mejor["peso_afinidad"]
    print(f"\nElegido: {mejor}")

    # 2. Entrenamiento final con todas las calificaciones
    pel_fin = peliculas_del_modelo(cal, pel, args.min_notas)
    ids_fin = pel_fin.id.to_numpy()
    V, s = factorizar(cal[cal.pelicula_id.isin(ids_fin)], ids_fin)
    X = vectores(V, s, k)
    cat_fin = catalogo_ml(pel_fin, cal)

    meta = {
        "fecha": date.today().isoformat(), "k": k, "prior": prior, "peso_afinidad": w, "min_notas": args.min_notas,
        "peliculas": len(ids_fin), "peliculas_con_plataforma": sum(bool(p["plataformas"]) for p in cat_fin),
        "calificaciones": int(cal.pelicula_id.isin(ids_fin).sum()),
        "varianza_explicada_k": round(float((s[:k] ** 2).sum() / (s ** 2).sum()), 4),
    }
    ARTEFACTOS.mkdir(parents=True, exist_ok=True)
    np.save(ARTEFACTOS / "vectores.npy", X)
    (ARTEFACTOS / "catalogo_ml.json").write_text(json.dumps(cat_fin, ensure_ascii=False, separators=(",", ":")))
    (ARTEFACTOS / "meta.json").write_text(json.dumps(meta, indent=2))
    (RAIZ / "ml" / "metricas.json").write_text(json.dumps(
        {"config": {"min_notas": args.min_notas, "fraccion_test": FRACCION_TEST, "relevante": RELEVANTE, "top": TOP,
                    "split": "temporal por usuario", "peliculas_eval": len(ids_ev)},
         "elegido": mejor,
         "resultados": resultados, "final": meta}, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
