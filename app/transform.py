"""Transformaciones económicas. Los números que ve el usuario salen de aquí, no del LLM."""
from __future__ import annotations

import pandas as pd


def inflacion_12m(indice: pd.DataFrame) -> pd.DataFrame:
    """Variación % a 12 meses de un índice mensual."""
    d = indice.sort_values("fecha").reset_index(drop=True).copy()
    d["valor"] = (d["valor"] / d["valor"].shift(12) - 1) * 100
    return d.dropna().reset_index(drop=True)


def var_mensual(indice: pd.DataFrame) -> pd.DataFrame:
    d = indice.sort_values("fecha").reset_index(drop=True).copy()
    d["valor"] = (d["valor"] / d["valor"].shift(1) - 1) * 100
    return d.dropna().reset_index(drop=True)


def acumulada_12m_desde_mensual(var_pct_mensual: pd.DataFrame) -> pd.DataFrame:
    """Compone 12 variaciones mensuales (en %) en la variación acumulada a 12 meses."""
    d = var_pct_mensual.sort_values("fecha").reset_index(drop=True).copy()
    factor = 1 + d["valor"] / 100
    d["valor"] = (factor.rolling(12).apply(lambda x: x.prod(), raw=True) - 1) * 100
    return d.dropna().reset_index(drop=True)


def a_mensual(diaria: pd.DataFrame) -> pd.DataFrame:
    """Promedio mensual de una serie diaria."""
    d = diaria.copy()
    d["fecha"] = d["fecha"].dt.to_period("M").dt.to_timestamp()
    return d.groupby("fecha", as_index=False)["valor"].mean()


def variacion_pct(serie: pd.DataFrame, periodos: int) -> float:
    """Variación % del último dato frente a 'periodos' atrás."""
    d = serie.dropna().sort_values("fecha")
    if len(d) <= periodos:
        raise ValueError("No hay suficientes datos")
    return float((d["valor"].iloc[-1] / d["valor"].iloc[-1 - periodos] - 1) * 100)


def percentil_historico(serie: pd.DataFrame, valor: float) -> float:
    """Porcentaje de observaciones históricas menores o iguales al valor (0 a 100)."""
    s = serie["valor"].dropna()
    return float((s <= valor).mean() * 100)


def ultimo_dato(serie: pd.DataFrame) -> dict:
    d = serie.dropna().sort_values("fecha").iloc[-1]
    return {"fecha": d["fecha"].strftime("%Y-%m-%d"), "valor": float(d["valor"])}
