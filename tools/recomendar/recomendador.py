"""Núcleo del recomendador de PromptCorn: lógica pura con numpy, sin AWS.

Lo usan tanto la Lambda (handler.py) como la evaluación offline (ml/entrenar.py),
así que lo que se mide es exactamente lo que corre en producción.

Entradas:
  vectores  (n, k) float32, un vector L2-normalizado por película (fila i <-> catalogo[i])
  catalogo  lista de dicts: id, titulo, anio, duracion_min, generos, plataformas,
            popularidad y calidad (0..1; el campo `prior` se mezcla con la afinidad)
"""
from __future__ import annotations

import numpy as np

NOTA_NEUTRA = 3.0          # un 3 no aporta; un 5 suma +2; un 1 resta -2
PESO_NO_ME_INTERESA = -1.0  # "no me interesa" resta como una nota de 2
PESO_PARECIDO = 0.8         # peso de la afinidad en el modo "parecida a X"
CAMPOS_EXTRA = ("generos", "duracion_min", "sinopsis", "poster")  # se copian a la respuesta si existen


class Recomendador:
    def __init__(self, vectores: np.ndarray, catalogo: list[dict], peso_afinidad: float = 0.5,
                 prior: str = "popularidad"):
        self.V = np.asarray(vectores, dtype=np.float32)
        self.catalogo = catalogo
        self.peso = peso_afinidad
        self.fila = {p["id"]: i for i, p in enumerate(catalogo)}
        self.prior = np.array([p[prior] for p in catalogo], dtype=np.float32)
        self.anio = np.array([p.get("anio") or 0 for p in catalogo])
        self.duracion = np.array([p.get("duracion_min") or 0 for p in catalogo])
        self._generos, self.G = self._matriz(p["generos"] for p in catalogo)
        self._plataformas, self.P = self._matriz(p["plataformas"] for p in catalogo)

    @staticmethod
    def _matriz(listas) -> tuple[dict[str, int], np.ndarray]:
        """Lista de etiquetas por película -> matriz booleana (n, n_etiquetas)."""
        listas = list(listas)
        indice = {e: j for j, e in enumerate(sorted({e for xs in listas for e in xs}))}
        m = np.zeros((len(listas), len(indice)), dtype=bool)
        for i, xs in enumerate(listas):
            m[i, [indice[e] for e in xs]] = True
        return indice, m

    # ---------- puntajes ----------

    def pesos_perfil(self, notas: dict[int, float] | None, descartadas=()) -> dict[int, float]:
        """Fila del catálogo -> peso en el perfil. Las películas fuera del modelo se ignoran."""
        pesos = {}
        for pid, nota in (notas or {}).items():
            if pid in self.fila and nota is not None:
                pesos[self.fila[pid]] = float(nota) - NOTA_NEUTRA
        for pid in descartadas:
            if pid in self.fila:
                pesos.setdefault(self.fila[pid], PESO_NO_ME_INTERESA)
        return {i: w for i, w in pesos.items() if w != 0}

    def puntajes(self, pesos: dict[int, float]) -> tuple[np.ndarray | None, np.ndarray]:
        """(afinidad, puntaje final) para todo el catálogo. Sin perfil: arranque en frío solo con el prior."""
        if not pesos:
            return None, self.prior.copy()
        idx = np.fromiter(pesos.keys(), dtype=int)
        w = np.fromiter(pesos.values(), dtype=np.float32)
        perfil = w @ self.V[idx]
        norma = np.linalg.norm(perfil)
        if norma == 0:
            return None, self.prior.copy()
        afinidad = self.V @ (perfil / norma)
        return afinidad, self.peso * afinidad + (1 - self.peso) * self.prior

    def puntajes_parecido(self, pid: int) -> tuple[np.ndarray, np.ndarray]:
        """"Parecida a X": el perfil es el vector de X. Pesa más la afinidad que en el modo perfil, para que
        lo popular no tape a lo parecido (este modo no tiene métrica offline; se ajustó a mano)."""
        afinidad = self.V @ self.V[self.fila[pid]]
        return afinidad, PESO_PARECIDO * afinidad + (1 - PESO_PARECIDO) * self.prior

    # ---------- filtros ----------

    @property
    def generos_validos(self) -> list[str]:
        return list(self._generos)

    @property
    def plataformas_validas(self) -> list[str]:
        return list(self._plataformas)

    def mascara(self, excluir=(), generos=None, duracion_max=None, anio_min=None, anio_max=None,
                plataformas=None, solo_disponibles=False) -> np.ndarray:
        """Filtros duros. plataformas: al menos una en común. solo_disponibles: en alguna plataforma de Perú."""
        ok = np.ones(len(self.catalogo), dtype=bool)
        if solo_disponibles:
            ok &= self.P.any(axis=1)
        filas = [self.fila[p] for p in excluir if p in self.fila]
        ok[filas] = False
        if generos:
            cols = [self._generos[g] for g in generos if g in self._generos]
            ok &= self.G[:, cols].any(axis=1) if cols else False
        if plataformas:
            cols = [self._plataformas[p] for p in plataformas if p in self._plataformas]
            ok &= self.P[:, cols].any(axis=1) if cols else False
        if duracion_max:
            ok &= (self.duracion > 0) & (self.duracion <= duracion_max)
        if anio_min:
            ok &= self.anio >= anio_min
        if anio_max:
            ok &= self.anio <= anio_max
        return ok

    # ---------- API ----------

    def recomendar(self, notas: dict[int, float] | None = None, descartadas=(), excluir=(), n: int = 3,
                   parecido_a: int | None = None, **filtros) -> list[dict]:
        """Top-n del catálogo que pasa los filtros, con el motivo de cada recomendación.

        notas: {id: calificación 0.5..5} de lo que el usuario vio y calificó.
        descartadas: ids marcados "no me interesa" (se excluyen y restan en el perfil).
        excluir: ids que no deben salir (vistas sin nota, recomendadas hace poco...).
        filtros: generos, duracion_max, anio_min, anio_max, plataformas, solo_disponibles.
        """
        notas = notas or {}
        if parecido_a is not None and parecido_a in self.fila:
            pesos = {self.fila[parecido_a]: 1.0}
            afinidad, total = self.puntajes_parecido(parecido_a)
        else:
            pesos = self.pesos_perfil(notas, descartadas)
            afinidad, total = self.puntajes(pesos)

        ok = self.mascara(excluir=[*notas, *descartadas, *excluir, *([parecido_a] if parecido_a else [])], **filtros)
        candidatas = np.flatnonzero(ok)
        if candidatas.size == 0:
            return []
        top = candidatas[np.argsort(-total[candidatas], kind="stable")[:n]]
        return [self._resultado(j, pesos, afinidad, notas) for j in top]

    def _resultado(self, j: int, pesos: dict[int, float], afinidad, notas) -> dict:
        p = self.catalogo[j]
        out = {"id": p["id"], "titulo": p["titulo"], "anio": p.get("anio"), "plataformas": p["plataformas"],
               **{c: p[c] for c in CAMPOS_EXTRA if c in p},
               "afinidad": None if afinidad is None else round(float(afinidad[j]), 3), "motivo": None}
        if pesos:
            filas = np.fromiter(pesos.keys(), dtype=int)
            aporte = np.fromiter(pesos.values(), dtype=np.float32) * (self.V[filas] @ self.V[j])
            mejor = int(np.argmax(aporte))
            if aporte[mejor] > 0:
                ref = self.catalogo[filas[mejor]]
                out["motivo"] = {"id": ref["id"], "titulo": ref["titulo"], "calificacion": notas.get(ref["id"])}
        return out
