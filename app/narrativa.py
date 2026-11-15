"""Resúmenes en lenguaje simple de los últimos 6 meses y del último año.

Todo número sale de los datos. El texto es una plantilla: no usa IA, así que no puede inventar cifras.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app import transform as T
from app.data import analitica, cargar, info

MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"]

# tipo: nivel (se compara % de cambio) | tasa (ya es un %, se compara en puntos) | estacional (suma de 6 meses vs año previo)
# palabras: cómo suena la serie en la calle
LENGUAJE = {
    "tc_interbancario_venta": dict(tipo="nivel", mensual=True, nombre="el precio del dólar", unidad="soles", dec=3,
                                   sube="el dólar se encareció", baja="el dólar se abarató"),
    "tc_interbancario_prom_mensual": dict(tipo="nivel", nombre="el precio del dólar", unidad="soles", dec=3,
                                          sube="el dólar se encareció", baja="el dólar se abarató"),
    "ipc_lima": dict(tipo="tasa", nombre="la inflación (cuánto subieron los precios en 12 meses)", unidad="%", dec=1,
                     sube="los precios suben más rápido", baja="los precios suben más lento"),
    "ipc_alimentos_var": dict(tipo="tasa", nombre="la variación de precios de alimentos y bebidas", unidad="%", dec=2,
                              sube="los alimentos subieron más", baja="los alimentos subieron menos"),
    "pbi_mensual_yoy": dict(tipo="tasa", nombre="el crecimiento de la economía frente al mismo mes del año pasado",
                            unidad="%", dec=1, sube="la economía crece más", baja="la economía crece menos"),
    "tasa_referencia": dict(tipo="tasa", nombre="la tasa de interés que fija el Banco Central", unidad="%", dec=2,
                            sube="el crédito tiende a encarecerse", baja="el crédito tiende a abaratarse"),
    "harina_precio": dict(tipo="nivel", nombre="el precio de la harina de pescado", unidad="US$ por tonelada", dec=0,
                          sube="la harina se encareció", baja="la harina se abarató"),
    "harina_export_fob": dict(tipo="nivel", nombre="lo que Perú vende al exterior en harina de pescado",
                              unidad="millones de US$", dec=1, sube="se exportó más valor", baja="se exportó menos valor"),
    "pbi_pesca_yoy": dict(tipo="tasa", nombre="el crecimiento de la pesca frente al año pasado", unidad="%", dec=1,
                          sube="la pesca crece más", baja="la pesca crece menos o cae"),
    "pbi_pesca_indice": dict(tipo="nivel", nombre="el nivel de producción de la pesca", unidad="puntos", dec=1,
                             sube="la producción pesquera subió", baja="la producción pesquera bajó"),
    "pbi_pecuario_yoy": dict(tipo="tasa", nombre="el crecimiento de la crianza de animales frente al año pasado",
                             unidad="%", dec=1, sube="crece más", baja="crece menos o cae"),
}
for _sid, _n in (("desempleo_lima", "el desempleo en Lima"), ("desempleo_lima_hombre", "el desempleo de hombres en Lima"),
                 ("desempleo_lima_mujer", "el desempleo de mujeres en Lima"),
                 ("desempleo_lima_14_24", "el desempleo de jóvenes (14 a 24 años) en Lima")):
    LENGUAJE[_sid] = dict(tipo="tasa", nombre=_n, unidad="%", dec=1, sube="hay más gente sin empleo",
                          baja="hay menos gente sin empleo")
for _sid, _r in (("anchoveta_total", "todo el país"), ("anchoveta_piura", "Piura"), ("anchoveta_la_libertad", "La Libertad"),
                 ("anchoveta_ancash", "Áncash"), ("anchoveta_lima", "Lima"), ("anchoveta_ica", "Ica")):
    LENGUAJE[_sid] = dict(tipo="estacional", nombre=f"la pesca de anchoveta en {_r}", unidad="toneladas", dec=0,
                          sube="se pescó más", baja="se pescó menos")


def mes_texto(f) -> str:
    f = pd.Timestamp(f)
    return f"{MESES_ES[f.month - 1]} de {f.year}"


def _num(v: float, dec: int) -> str:
    return f"{v:,.{dec}f}"


def _serie_base(sid: str, series_dir: Path | None) -> pd.DataFrame:
    lg = LENGUAJE.get(sid, {})
    if sid == "ipc_lima":
        return analitica(sid, series_dir)
    raw = cargar(sid, series_dir)
    return T.a_mensual(raw) if lg.get("mensual") else raw


def _en(d: pd.DataFrame, fecha: pd.Timestamp):
    f = d[d["fecha"] == fecha]
    return None if f.empty else float(f["valor"].iloc[0])


def resumen(sid: str, series_dir: Path | None = None) -> dict:
    """Devuelve cifras y frases en lenguaje simple sobre los últimos 6 meses y el último año."""
    meta = info(sid)
    lg = LENGUAJE.get(sid) or dict(tipo="tasa" if "%" in meta["unidad"] else "nivel", nombre=meta["nombre"],
                                   unidad=meta["unidad"], dec=2, sube="subió", baja="bajó")
    d = _serie_base(sid, series_dir).dropna().sort_values("fecha").reset_index(drop=True)
    if len(d) < 13:
        raise ValueError("Pocos datos para resumir")
    ult = d.iloc[-1]
    f_ult = pd.Timestamp(ult["fecha"])
    v_ult = float(ult["valor"])
    dec, uni, tipo = lg["dec"], lg["unidad"], lg["tipo"]
    out = {"id": sid, "fecha_ultimo": f_ult.strftime("%Y-%m-%d"), "valor_ultimo": v_ult, "tipo": tipo, "frases": []}
    ult12 = d[d["fecha"] > f_ult - pd.DateOffset(months=12)]
    out["max12"] = {"valor": float(ult12["valor"].max()),
                    "fecha": pd.Timestamp(ult12.loc[ult12["valor"].idxmax(), "fecha"]).strftime("%Y-%m-%d")}
    out["min12"] = {"valor": float(ult12["valor"].min()),
                    "fecha": pd.Timestamp(ult12.loc[ult12["valor"].idxmin(), "fecha"]).strftime("%Y-%m-%d")}

    if tipo == "estacional":
        suma = d["valor"].rolling(6).sum()
        s6, s6_prev = suma.iloc[-1], suma.iloc[-13] if len(suma) >= 13 else None
        out["acum6"] = float(s6)
        if s6_prev and s6_prev > 0:
            var = (s6 / s6_prev - 1) * 100
            out["var6_vs_anio_previo"] = float(var)
            verbo = lg["sube"] if var > 0 else lg["baja"]
            out["frases"].append(
                f"En los últimos 6 meses (hasta {mes_texto(f_ult)}) se desembarcaron {_num(s6, 0)} toneladas en total, "
                f"{abs(var):.0f}% {'más' if var > 0 else 'menos'} que en el mismo período del año anterior: {verbo}. "
                f"La pesca de anchoveta es por temporadas, por eso se compara con el mismo período del año pasado y no con el mes anterior.")
        s12 = d["valor"].iloc[-12:].sum()
        s12_prev = d["valor"].iloc[-24:-12].sum() if len(d) >= 24 else None
        out["acum12"] = float(s12)
        if s12_prev and s12_prev > 0:
            var12 = (s12 / s12_prev - 1) * 100
            out["var12"] = float(var12)
            out["frases"].append(f"En el último año se pescaron {_num(s12, 0)} toneladas, {abs(var12):.0f}% "
                                 f"{'más' if var12 > 0 else 'menos'} que el año anterior.")
        out["frases"].append(f"El mes más fuerte del último año fue {mes_texto(out['max12']['fecha'])} "
                             f"({_num(out['max12']['valor'], 0)} t).")
        return out

    v6 = _en(d, f_ult - pd.DateOffset(months=6))
    v12 = _en(d, f_ult - pd.DateOffset(months=12))
    out["hace6"], out["hace12"] = v6, v12
    for etiqueta, previo, clave in (("En los últimos 6 meses", v6, "cambio6"), ("En el último año", v12, "cambio12")):
        if previo is None:
            continue
        if tipo == "nivel":
            cambio = (v_ult / previo - 1) * 100
            out[clave] = float(cambio)
            verbo = lg["sube"] if cambio > 0 else lg["baja"]
            out["frases"].append(
                f"{etiqueta} {verbo}: pasó de {_num(previo, dec)} a {_num(v_ult, dec)} {uni} "
                f"({'+' if cambio > 0 else '−'}{abs(cambio):.1f}%).")
        else:
            cambio = v_ult - previo
            out[clave] = float(cambio)
            verbo = lg["sube"] if cambio > 0 else lg["baja"]
            out["frases"].append(
                f"{etiqueta}, {lg['nombre']} pasó de {_num(previo, dec)}% a {_num(v_ult, dec)}% "
                f"({'+' if cambio > 0 else '−'}{abs(cambio):.1f} puntos): {verbo}.")
    out["frases"].append(
        f"En el último año el valor más alto fue {_num(out['max12']['valor'], dec)} ({mes_texto(out['max12']['fecha'])}) "
        f"y el más bajo {_num(out['min12']['valor'], dec)} ({mes_texto(out['min12']['fecha'])}).")
    pct = T.percentil_historico(d, v_ult)
    out["percentil"] = pct
    out["frases"].append(
        f"Comparado con toda su historia desde {d['fecha'].iloc[0].year}, el valor actual está más alto que el {pct:.0f}% de los meses.")
    return out


def texto(sid: str, series_dir: Path | None = None) -> str:
    try:
        return " ".join(resumen(sid, series_dir)["frases"])
    except (FileNotFoundError, ValueError, KeyError):
        return "Todavía no hay datos suficientes para resumir esta serie."
