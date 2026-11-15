"""Acceso a BCRPData: interpretación de fechas, respuesta de la API y lectura de CSV.

IMPORTANTE: el formato de la API se escribió a partir de la documentación general de
BCRPData y NO se ha probado contra el servidor real (el entorno de desarrollo no tenía
acceso). La primera corrida de scripts/fetch_bcrp.py debe revisarse a mano.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "set": 9, "sep": 9, "oct": 10, "nov": 11, "dic": 12}

API_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{desde}/{hasta}/esp"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip().lower()


def _anio(y: str) -> int:
    n = int(y)
    if n >= 100:
        return n
    return 2000 + n if n <= 69 else 1900 + n


def parse_period(name: str) -> date:
    """Convierte etiquetas como 'Ene.2020', 'Ene20', '02.Ene.20', 'T1.2020' o '2020' en fecha."""
    s = _norm(str(name))
    m = re.fullmatch(r"(?:(\d{1,2})[.\s/-]*)?([a-z]{3})[.\s/-]*(\d{2,4})", s)
    if m and m.group(2) in MESES:
        dia = int(m.group(1)) if m.group(1) else 1
        return date(_anio(m.group(3)), MESES[m.group(2)], dia)
    m = re.fullmatch(r"t([1-4])[.\s/-]*(\d{2,4})", s)
    if m:
        return date(_anio(m.group(2)), (int(m.group(1)) - 1) * 3 + 1, 1)
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return date(int(m.group(1)), 1, 1)
    raise ValueError(f"Etiqueta de periodo no reconocida: {name!r}")


def _to_float(v) -> float:
    if v is None:
        return float("nan")
    t = str(v).strip().replace(",", "")
    if t in ("", "n.d.", "nd", "-", "n.a."):
        return float("nan")
    try:
        return float(t)
    except ValueError:
        return float("nan")


def parse_api_json(payload: dict | str) -> pd.DataFrame:
    """Respuesta de la API -> DataFrame con columnas fecha, valor (una serie)."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    periodos = payload.get("periods", [])
    filas = [(parse_period(p["name"]), _to_float(p["values"][0] if p.get("values") else None))
             for p in periodos]
    df = pd.DataFrame(filas, columns=["fecha", "valor"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.sort_values("fecha").reset_index(drop=True)


def fetch_series(session, code: str, desde: str, hasta: str, timeout: int = 30) -> pd.DataFrame:
    """Descarga una serie. 'desde'/'hasta' en formato 'YYYY-M' (mensual) o 'YYYY-M-D' (diaria)."""
    r = session.get(API_URL.format(code=code, desde=desde, hasta=hasta), timeout=timeout)
    r.raise_for_status()
    try:
        return parse_api_json(r.json())
    except ValueError as e:
        raise ValueError(f"Respuesta inesperada para {code}: {r.text[:200]!r}") from e


def save_series(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def load_series(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["fecha"])
    return df.sort_values("fecha").reset_index(drop=True)


def load_export_csv(path: Path) -> pd.DataFrame:
    """Plan B: CSV exportado a mano desde BCRPData (dos columnas: periodo, valor)."""
    raw = pd.read_csv(path, header=None, skiprows=1, usecols=[0, 1])
    filas = [(parse_period(a), _to_float(b)) for a, b in raw.itertuples(index=False)]
    df = pd.DataFrame(filas, columns=["fecha", "valor"])
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.sort_values("fecha").reset_index(drop=True)
