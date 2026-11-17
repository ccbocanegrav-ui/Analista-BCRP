"""Semáforo de exposición. Reglas explícitas y visibles; no es un pronóstico ni una recomendación.

Cada indicador se compara con su PROPIA historia: se calcula en qué percentil cae su último valor.
Si el movimiento es adverso para el perfil, un percentil alto (o bajo, según el sentido) es señal de alerta.
Umbrales: rojo si el percentil adverso >= 80; amarillo si >= 60; verde en otro caso.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from app import transform as T
from app.data import analitica, cargar

UMBRAL_ROJO = 80
UMBRAL_AMARILLO = 60

ADVERTENCIA = ("Criterio de Termómetro basado en la historia de cada dato. "
               "No es un pronóstico ni una recomendación de inversión o de negocio. "
               "Que dos cosas pasen a la vez no significa que una cause la otra.")


@dataclass
class Indicador:
    clave: str
    nombre: str
    valor: float | None
    unidad: str
    fecha: str | None
    color: str          # rojo | amarillo | verde | gris
    razon: str
    sentido: str = "alza"
    umbral_amarillo: float | None = None   # valor a partir del cual el indicador pasa a amarillo
    umbral_rojo: float | None = None       # valor a partir del cual pasa a rojo


# clave -> especificación del indicador
ESPECIFICACIONES = {
    "tc_var12": dict(nombre="Tipo de cambio (var. a 12 meses)", sid="tc_interbancario_prom_mensual",
                     calculo=("var", 12), unidad="%"),
    "inflacion": dict(nombre="Inflación Lima (12 meses)", sid="ipc_lima", calculo=("analitica", None), unidad="%"),
    "pbi_yoy": dict(nombre="PBI mensual (var. interanual)", sid="pbi_mensual_yoy", calculo=("analitica", None), unidad="%"),
    "harina_precio": dict(nombre="Precio de harina de pescado (var. 12 meses)", sid="harina_precio",
                          calculo=("var", 12), unidad="%"),
    "anchoveta_6m": dict(nombre="Desembarque de anchoveta (6 meses vs año previo)", sid="anchoveta_total",
                         calculo=("acum", 6), unidad="%"),
    "pbi_pesca": dict(nombre="PBI pesca (var. interanual)", sid="pbi_pesca_yoy", calculo=("analitica", None), unidad="%"),
}

# perfil -> lista de (clave, sentido adverso). "alza": preocupa que suba; "baja": preocupa que baje.
PERFILES = {
    "Importador (insumos o mercadería en dólares)": [("tc_var12", "alza"), ("inflacion", "alza"), ("pbi_yoy", "baja")],
    "Comercio y venta de alimentos": [("inflacion", "alza"), ("tc_var12", "alza"), ("pbi_yoy", "baja")],
    "Exportador (ingresos en dólares)": [("tc_var12", "baja"), ("pbi_yoy", "baja")],
    "Pesca y harina de pescado": [("harina_precio", "baja"), ("anchoveta_6m", "baja"), ("pbi_pesca", "baja")],
}


def _historia(spec: dict, series_dir: Path | None):
    kind, n = spec["calculo"]
    if kind == "analitica":
        return analitica(spec["sid"], series_dir)
    raw = cargar(spec["sid"], series_dir)
    return T.serie_variacion(raw, n) if kind == "var" else T.acumulado_interanual(raw, n)


def evaluar_indicador(clave: str, sentido: str, series_dir: Path | None = None) -> Indicador:
    spec = ESPECIFICACIONES[clave]
    try:
        hist = _historia(spec, series_dir)
        ultimo = T.ultimo_dato(hist)
    except (FileNotFoundError, ValueError, IndexError) as e:
        return Indicador(clave, spec["nombre"], None, spec["unidad"], None, "gris", f"Sin datos suficientes ({e})", sentido)
    pct = T.percentil_historico(hist, ultimo["valor"])
    adverso = pct if sentido == "alza" else 100 - pct
    color = "rojo" if adverso >= UMBRAL_ROJO else "amarillo" if adverso >= UMBRAL_AMARILLO else "verde"
    texto_sentido = "alto" if sentido == "alza" else "bajo"
    # En palabras simples (una usuaria no entendió "percentil 85"; ver docs/research/entrevista-1.md).
    desde = str(hist["fecha"].min())[:4]
    razon = (f"{ultimo['valor']:.1f}{spec['unidad']} a {ultimo['fecha'][:7]}: está más {texto_sentido} que en "
             f"{adverso:.0f} de cada 100 meses desde {desde}. Para este tipo de negocio, lo preocupante es que esté "
             f"{texto_sentido}. Se pone rojo cuando está más {texto_sentido} que en {UMBRAL_ROJO} de cada 100 meses "
             f"y amarillo desde {UMBRAL_AMARILLO}.")
    serie = hist["valor"].dropna()
    if sentido == "alza":
        u_am, u_ro = float(serie.quantile(UMBRAL_AMARILLO / 100)), float(serie.quantile(UMBRAL_ROJO / 100))
    else:
        u_am, u_ro = float(serie.quantile(1 - UMBRAL_AMARILLO / 100)), float(serie.quantile(1 - UMBRAL_ROJO / 100))
    return Indicador(clave, spec["nombre"], ultimo["valor"], spec["unidad"], ultimo["fecha"], color, razon,
                     sentido, u_am, u_ro)


TERMOMETRO = [   # (clave, sentido adverso, nombre simple, frase si preocupa)
    ("inflacion", "alza", "Precios", "los precios están subiendo rápido"),
    ("tc_var12", "alza", "Dólar", "el dólar está subiendo"),
    ("pbi_yoy", "baja", "Ventas en la economía", "la economía crece poco"),
    ("anchoveta_6m", "baja", "Pesca", "se está pescando poco"),
]


def termometro_general(series_dir: Path | None = None) -> dict:
    """Un solo número de 0 a 100 para "cómo está el clima para los negocios": promedio de qué tan preocupante está
    cada factor frente a su propia historia (0 = su mejor momento para un negocio, 100 = el peor). Pesos iguales."""
    from app import nino
    comps = []
    for clave, sentido, nombre, frase in TERMOMETRO:
        i = evaluar_indicador(clave, sentido, series_dir)
        if i.color == "gris":
            continue
        pct = T.percentil_historico(_historia(ESPECIFICACIONES[clave], series_dir), i.valor)
        comps.append({"nombre": nombre, "puntaje": round(pct if sentido == "alza" else 100 - pct), "frase": frase})
    anom = nino.anomalia_mensual(series_dir)
    if anom is not None and not anom.empty:
        pct = T.percentil_historico(anom, float(anom.sort_values("fecha")["valor"].iloc[-1]))
        comps.append({"nombre": "El Niño (mar caliente)", "puntaje": round(pct), "frase": "el mar está muy caliente"})
    if not comps:
        return {"puntaje": None, "color": "gris", "titulo": "Sin datos", "componentes": []}
    for c in comps:
        c["color"] = "rojo" if c["puntaje"] >= UMBRAL_ROJO else "amarillo" if c["puntaje"] >= UMBRAL_AMARILLO else "verde"
    puntaje = round(sum(c["puntaje"] for c in comps) / len(comps))
    color = "rojo" if puntaje >= 65 else "amarillo" if puntaje >= 45 else "verde"
    titulo = {"rojo": "Clima difícil para los negocios", "amarillo": "Atención: hay factores que preocupan",
              "verde": "Clima tranquilo para los negocios"}[color]
    preocupan = [c["frase"] for c in sorted(comps, key=lambda c: -c["puntaje"]) if c["color"] == "rojo"]
    return {"puntaje": puntaje, "color": color, "titulo": titulo, "componentes": comps, "preocupan": preocupan}


def evaluar(perfil: str, series_dir: Path | None = None) -> dict:
    inds = [evaluar_indicador(c, s, series_dir) for c, s in PERFILES[perfil]]
    con_datos = [i for i in inds if i.color != "gris"]
    rojos = sum(i.color == "rojo" for i in con_datos)
    amarillos = sum(i.color == "amarillo" for i in con_datos)
    general = "gris" if not con_datos else "rojo" if rojos >= 2 else "amarillo" if (rojos == 1 or amarillos >= 2) else "verde"
    return {"perfil": perfil, "general": general, "indicadores": [asdict(i) for i in inds], "advertencia": ADVERTENCIA}
