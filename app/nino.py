"""Contenido explicativo sobre El Niño costero para emprendedores y análisis de episodios.

El texto es de divulgación y debe contrastarse con los comunicados del ENFEN y los reportes del BCRP.
Las cifras económicas salen de los datos descargados (app/geo.py), no de este archivo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.data import externa

QUE_ES = (
    "El Niño costero es un calentamiento anormal del mar frente a las costas de Perú. Cuando el agua se calienta, "
    "cambian las lluvias en la costa y la anchoveta, un pez de agua fría, se aleja o se vuelve escasa. "
    "Un comité de entidades del Estado, el ENFEN, vigila el mar, emite comunicados y declara estados de alerta."
)

CANALES = [
    ("Pesca", "Menos anchoveta significa menos toneladas para harina y aceite de pescado, menos trabajo en puertos y plantas, "
              "y un precio de la harina que puede moverse."),
    ("Agro", "Lluvias fuertes en el norte o calor excesivo pueden dañar cultivos y caminos. Menos cosecha o más costo de "
             "transporte puede subir los precios de algunos alimentos."),
    ("Precios y costos", "Si hay menos alimentos disponibles, los precios suben. Eso afecta a quien compra insumos, "
                         "a restaurantes, bodegas y a los hogares."),
    ("Transporte y comercio", "Lluvias intensas y huaicos pueden cortar carreteras, retrasar entregas y subir fletes."),
    ("Dólar y finanzas", "Si bajan las exportaciones de harina, entran menos dólares al país. Puede influir en el tipo de "
                         "cambio, aunque no es el único factor."),
]

GLOSARIO = {
    "Anomalía de temperatura": "Cuánto más caliente (o más frío) está el mar frente a lo normal para esa época. +1 °C significa 1 grado más que lo normal.",
    "Niño 1+2": "La zona del océano Pacífico frente a las costas de Perú y Ecuador. Es la que más se parece a lo que siente nuestra costa.",
    "Veda": "Período en que está prohibido pescar para proteger a la especie mientras se reproduce o crece.",
    "Temporada de pesca": "Períodos en que se autoriza la pesca de anchoveta. En el año hay dos: una en el primer semestre y otra en el segundo.",
    "Inflación": "Cuánto suben los precios de la canasta de los hogares frente al mismo mes del año pasado.",
    "Interanual": "Comparar un mes con el mismo mes del año anterior, para quitar el efecto de las estaciones.",
    "Percentil": "Si un valor está en el percentil 80, es más alto que el 80% de los meses de la historia de esa serie.",
    "Semáforo": "Criterio de la app: compara el valor actual con la historia de cada indicador. No es un pronóstico.",
}


def anomalia_mensual(series_dir=None) -> pd.DataFrame | None:
    """Anomalía de temperatura del mar (Niño 1+2) en promedio mensual, si el archivo de NOAA fue descargado."""
    d = externa("nino12_anomalia", series_dir)
    if d is None or d.empty:
        return None
    d = d.copy()
    d["fecha"] = d["fecha"].dt.to_period("M").dt.to_timestamp()
    return d.groupby("fecha", as_index=False)["valor"].mean()


def correlacion_con_pesca(anomalia: pd.DataFrame, pesca: pd.DataFrame) -> dict | None:
    """Correlación entre la anomalía del mar y la variación interanual de la pesca (descriptiva)."""
    p = pesca.sort_values("fecha").copy()
    p["yoy"] = (p["valor"].rolling(6).sum() / p["valor"].rolling(6).sum().shift(12) - 1) * 100
    d = anomalia.merge(p[["fecha", "yoy"]], on="fecha").replace([np.inf, -np.inf], np.nan).dropna()
    if len(d) < 24:
        return None
    return {"r": float(np.corrcoef(d["valor"], d["yoy"])[0, 1]), "n": int(len(d))}
