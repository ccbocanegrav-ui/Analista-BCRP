"""Exposición geográfica de la pesca de anchoveta y análisis de sensibilidad.

Cubre las regiones cuyas series están en el catálogo. Las coordenadas son del puerto principal
de cada región y son referenciales (sirven para ubicar la región en el mapa, no para medir distancias).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.data import cargar

REGIONES = {
    "anchoveta_piura": dict(nombre="Piura", puerto="Paita", lat=-5.09, lon=-81.11),
    "anchoveta_la_libertad": dict(nombre="La Libertad", puerto="Malabrigo", lat=-7.70, lon=-79.45),
    "anchoveta_ancash": dict(nombre="Áncash", puerto="Chimbote", lat=-9.07, lon=-78.59),
    "anchoveta_lima": dict(nombre="Lima", puerto="Huacho", lat=-11.11, lon=-77.61),
    "anchoveta_ica": dict(nombre="Ica", puerto="Pisco", lat=-13.71, lon=-76.20),
}
TOTAL = "anchoveta_total"

# Años con evento El Niño costero declarado (verificar fechas y magnitud en los comunicados del ENFEN).
EPISODIOS = {2017: "El Niño costero 2017", 2023: "El Niño costero 2023", 2026: "El Niño 2026 (en curso)"}
MES_INI, MES_FIN = 1, 8   # período comparable: 2026 solo tiene datos hasta agosto


def suma_periodo(df: pd.DataFrame, anio: int, mes_ini: int = MES_INI, mes_fin: int = MES_FIN) -> float | None:
    f = df[(df["fecha"].dt.year == anio) & (df["fecha"].dt.month >= mes_ini) & (df["fecha"].dt.month <= mes_fin)]
    if f["valor"].notna().sum() < (mes_fin - mes_ini + 1):
        return None
    return float(f["valor"].sum())


def serie_anual(sid: str, series_dir: Path | None = None) -> pd.DataFrame:
    """Toneladas de enero a agosto de cada año (comparable entre años)."""
    df = cargar(sid, series_dir)
    filas = []
    for a in sorted(df["fecha"].dt.year.unique()):
        v = suma_periodo(df, int(a))
        if v is not None:
            filas.append({"anio": int(a), "valor": v})
    return pd.DataFrame(filas)


def caida_en_episodio(sid: str, anio: int, series_dir: Path | None = None) -> float | None:
    """Variación % de enero–agosto del año del episodio frente al año anterior."""
    df = cargar(sid, series_dir)
    a, b = suma_periodo(df, anio), suma_periodo(df, anio - 1)
    if a is None or not b:
        return None
    return (a / b - 1) * 100


def tabla_regional(series_dir: Path | None = None) -> pd.DataFrame:
    filas = []
    total12 = None
    try:
        tot = cargar(TOTAL, series_dir).sort_values("fecha")
        total12 = float(tot["valor"].iloc[-12:].sum())
    except FileNotFoundError:
        pass
    for sid, r in REGIONES.items():
        try:
            df = cargar(sid, series_dir).sort_values("fecha")
        except FileNotFoundError:
            continue
        v12 = float(df["valor"].iloc[-12:].sum())
        fila = {"id": sid, **r, "toneladas_12m": v12}
        caidas = [c for a in EPISODIOS if (c := caida_en_episodio(sid, a, series_dir)) is not None]
        for a in EPISODIOS:
            fila[f"var_{a}"] = caida_en_episodio(sid, a, series_dir)
        negativas = [c for c in caidas if c < 0]
        fila["caida_promedio_episodios"] = float(np.mean(negativas)) if negativas else 0.0
        fila["toneladas_en_riesgo"] = v12 * abs(fila["caida_promedio_episodios"]) / 100
        filas.append(fila)
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    suma5 = df["toneladas_12m"].sum()
    df["participacion_pct"] = df["toneladas_12m"] / suma5 * 100 if suma5 else 0.0
    df.attrs["cobertura_pct"] = (suma5 / total12 * 100) if total12 else None
    return df


def escenario(tabla: pd.DataFrame, caida_pct: float) -> pd.DataFrame:
    """Toneladas que se dejarían de pescar en cada región si el volumen cae 'caida_pct' %."""
    t = tabla.copy()
    t["toneladas_perdidas"] = t["toneladas_12m"] * caida_pct / 100
    return t


def sensibilidad_precio_harina(series_dir: Path | None = None, ventana: int = 6) -> dict | None:
    """Relación histórica entre la variación interanual de la pesca y la del precio de la harina.

    Regresión lineal simple sobre ventanas móviles. Es descriptiva: no prueba causalidad ni pronostica.
    """
    try:
        an = cargar(TOTAL, series_dir).sort_values("fecha").set_index("fecha")["valor"]
        pr = cargar("harina_precio", series_dir).sort_values("fecha").set_index("fecha")["valor"]
    except FileNotFoundError:
        return None
    x = an.rolling(ventana).sum()
    x = (x / x.shift(12) - 1) * 100
    y = pr.rolling(ventana).mean()
    y = (y / y.shift(12) - 1) * 100
    d = pd.concat([x.rename("x"), y.rename("y")], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < 24 or d["x"].std() == 0:
        return None
    pend, intercepto = np.polyfit(d["x"], d["y"], 1)
    r = float(np.corrcoef(d["x"], d["y"])[0, 1])
    return {"pendiente": float(pend), "intercepto": float(intercepto), "r2": r ** 2, "n": int(len(d)),
            "datos": d.reset_index()}
