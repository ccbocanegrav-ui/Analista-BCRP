"""Acceso al catálogo y a las series descargadas. Solo existen las series del catálogo."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd

from app import transform as T
from app.bcrp import load_series

ROOT = Path(__file__).resolve().parents[1]
CATALOGO = ROOT / "data" / "catalog.json"
SERIES_DIR = Path(os.environ.get("TERMOMETRO_SERIES_DIR", ROOT / "data" / "series"))
FICHAS_DIR = ROOT / "data" / "fichas"


def catalogo() -> list[dict]:
    return json.loads(CATALOGO.read_text(encoding="utf-8"))["series"]


def info(sid: str) -> dict:
    for s in catalogo():
        if s["id"] == sid:
            return s
    raise KeyError(f"Serie fuera del catálogo: {sid}")


def cargar(sid: str, series_dir: Path | None = None) -> pd.DataFrame:
    info(sid)  # falla si no está en el catálogo
    ruta = (series_dir or SERIES_DIR) / f"{sid}.csv"
    if not ruta.exists():
        raise FileNotFoundError(f"No hay datos descargados para {sid}. Ejecuta scripts/fetch_bcrp.py")
    return load_series(ruta)


def analitica(sid: str, series_dir: Path | None = None) -> pd.DataFrame:
    """Serie lista para mostrar, aplicando la transformación del catálogo."""
    raw = cargar(sid, series_dir)
    if info(sid)["transformacion"] == "inflacion_12m":
        return T.inflacion_12m(raw)
    return raw


def ficha(sid: str) -> str | None:
    ruta = FICHAS_DIR / f"{sid}.md"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else None


def externa(nombre: str = "nino12_anomalia", series_dir: Path | None = None) -> pd.DataFrame | None:
    """Series externas opcionales (p. ej. NOAA). Devuelve None si no se descargaron."""
    ruta = (series_dir or SERIES_DIR) / f"{nombre}.csv"
    if not ruta.exists():
        return None
    return load_series(ruta)


def _tokens(texto: str) -> set[str]:
    return {t for t in re.findall(r"[a-záéíóúñ0-9]{4,}", texto.lower())}


def buscar_fichas(consulta: str, k: int = 3) -> list[dict]:
    """Recuperación simple por palabras sobre las fichas (la base del RAG)."""
    q = _tokens(consulta)
    res = []
    for ruta in sorted(FICHAS_DIR.glob("*.md")):
        txt = ruta.read_text(encoding="utf-8")
        puntaje = len(q & _tokens(txt)) + 3 * len(q & _tokens(ruta.stem.replace("_", " ")))
        if puntaje:
            res.append({"id": ruta.stem, "puntaje": puntaje, "texto": txt})
    return sorted(res, key=lambda r: -r["puntaje"])[:k]
