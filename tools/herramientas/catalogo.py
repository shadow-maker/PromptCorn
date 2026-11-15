"""Catálogo completo de PromptCorn en memoria (9,649 películas, se carga una vez por contenedor)."""
from __future__ import annotations

import difflib
import json
import re
import unicodedata


def _clave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


class Catalogo:
    def __init__(self, datos: dict, ids_externos: dict):
        self.fecha_disponibilidad = datos["fecha_disponibilidad"]
        self.peliculas = {p["id"]: p for p in datos["peliculas"]}
        # Traducción interna id propio <-> referencia de la API externa (nunca sale de las herramientas)
        self.ref_por_id = {int(k): int(v) for k, v in ids_externos.items()}
        self.id_por_ref = {v: k for k, v in self.ref_por_id.items()}
        self.plataformas = sorted({pl for p in self.peliculas.values() for pl in p["plataformas"]})
        self._titulos = [(pid, _clave(p["titulo"]), _clave(p.get("titulo_original", "")))
                         for pid, p in self.peliculas.items()]
        self._por_clave: dict[str, list[int]] = {}
        for pid, t, t_orig in self._titulos:
            for k in {t, t_orig} - {""}:
                self._por_clave.setdefault(k, []).append(pid)

    @classmethod
    def desde_bytes(cls, catalogo: bytes, ids_externos: bytes) -> "Catalogo":
        return cls(json.loads(catalogo), json.loads(ids_externos))

    def get(self, pid: int) -> dict | None:
        return self.peliculas.get(pid)

    def buscar_local(self, titulo: str, anio: int | None = None, limite: int = 5) -> list[dict]:
        """Búsqueda por título sin tildes ni mayúsculas (respaldo si la API externa no responde)."""
        q = _clave(titulo)
        if not q:
            return []
        exactos, contiene = [], []
        for pid, t, t_orig in self._titulos:
            if anio and self.peliculas[pid].get("anio") != anio:
                continue
            if q in (t, t_orig):
                exactos.append(pid)
            elif q in t or q in t_orig:
                contiene.append(pid)
        contiene.sort(key=lambda pid: len(self.peliculas[pid]["titulo"]))  # lo más parecido primero
        encontrados = exactos + contiene
        if not encontrados:  # errores de tipeo: "intersteller" -> "interstellar"
            for clave in difflib.get_close_matches(q, self._por_clave, n=limite, cutoff=0.8):
                encontrados += [pid for pid in self._por_clave[clave]
                                if pid not in encontrados and (not anio or self.peliculas[pid].get("anio") == anio)]
        return [self.peliculas[pid] for pid in encontrados[:limite]]
