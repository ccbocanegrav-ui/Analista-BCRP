"""Acceso al catálogo y a las series descargadas. Solo existen las series del catálogo."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app import transform as T
from app.bcrp import load_series

ROOT = Path(__file__).resolve().parents[1]
CATALOGO = ROOT / "data" / "catalog.json"
SERIES_DIR = ROOT / "data" / "series"
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
