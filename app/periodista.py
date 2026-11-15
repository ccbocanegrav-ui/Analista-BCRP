"""Modo periodista: los números los calcula el código; el texto se verifica contra esos números."""
from __future__ import annotations

import re
from pathlib import Path

from app import transform as T
from app.data import analitica, cargar, info

CODIGOS_USADOS = ["tc_interbancario_venta", "ipc_lima", "tasa_referencia", "pbi_mensual_yoy"]


def _fmt_fecha(f: str) -> str:
    return f[:7]


def hechos(series_dir: Path | None = None) -> list[dict]:
    """Lista de hechos {texto, valores, fuente}. Si falta una serie, ese hecho se omite."""
    out: list[dict] = []

    def agregar(sid, construir):
        try:
            out.append(construir())
        except (FileNotFoundError, ValueError, IndexError):
            pass

    def tc():
        mensual = T.a_mensual(cargar("tc_interbancario_venta", series_dir))
        u = T.ultimo_dato(cargar("tc_interbancario_venta", series_dir))
        v12 = T.variacion_pct(mensual, 12)
        return {"texto": f"El tipo de cambio interbancario (venta) cerró en S/ {u['valor']:.3f} por dólar al {u['fecha']}, "
                         f"y su promedio mensual varió {v12:.1f}% frente a hace 12 meses.",
                "valores": [u["valor"], v12], "fechas": [u["fecha"]], "fuente": info("tc_interbancario_venta")["code"]}

    def inflacion():
        u = T.ultimo_dato(analitica("ipc_lima", series_dir))
        return {"texto": f"La inflación de Lima Metropolitana a 12 meses fue {u['valor']:.1f}% en {_fmt_fecha(u['fecha'])}.",
                "valores": [u["valor"]], "fechas": [u["fecha"]], "fuente": info("ipc_lima")["code"]}

    def tasa():
        u = T.ultimo_dato(cargar("tasa_referencia", series_dir))
        return {"texto": f"La tasa de referencia de política monetaria del BCRP se ubicó en {u['valor']:.2f}% en {_fmt_fecha(u['fecha'])}.",
                "valores": [u["valor"]], "fechas": [u["fecha"]], "fuente": info("tasa_referencia")["code"]}

    def pbi():
        u = T.ultimo_dato(cargar("pbi_mensual_yoy", series_dir))
        return {"texto": f"El PBI creció {u['valor']:.1f}% interanual en {_fmt_fecha(u['fecha'])}.",
                "valores": [u["valor"]], "fechas": [u["fecha"]], "fuente": info("pbi_mensual_yoy")["code"]}

    for sid, fn in (("tc", tc), ("ipc", inflacion), ("tasa", tasa), ("pbi", pbi)):
        agregar(sid, fn)
    return out


def nota_plantilla(hs: list[dict]) -> str:
    if not hs:
        return "No hay datos descargados para redactar la nota."
    cuerpo = " ".join(h["texto"] for h in hs)
    fuentes = ", ".join(sorted({h["fuente"] for h in hs}))
    return f"{cuerpo}\nFuente: BCRPData (series {fuentes})."


_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def numeros_permitidos(hs: list[dict]) -> set[str]:
    perm: set[str] = {"12"}  # ventana fija de "12 meses" que usan las plantillas
    for h in hs:
        for v in h["valores"]:
            for dec in (0, 1, 2, 3):
                perm.add(f"{abs(v):.{dec}f}")
                perm.add(f"{v:.{dec}f}")
        for f in h.get("fechas", []):
            perm.update(re.findall(r"\d+", f))
            perm.update(str(int(x)) for x in re.findall(r"\d+", f))
        perm.update(re.findall(r"\d+", h["fuente"]))
    return perm


def verificar_numeros(texto: str, hs: list[dict]) -> list[str]:
    """Devuelve los números del texto que NO provienen de los datos. Lista vacía = texto verificado."""
    perm = numeros_permitidos(hs)
    malos = []
    for m in _NUM.findall(texto):
        n = m.replace(",", ".")
        if n in perm or n.lstrip("-") in perm:
            continue
        if re.fullmatch(r"(19|20)\d{2}", n):  # años
            continue
        malos.append(m)
    return malos
