"""Sensibilidad del margen de un negocio frente al dólar y a los precios de insumos.

Modelo simple y transparente: ingresos = 100; costos = 100 − margen. Una parte de los ingresos y de los costos
está atada al dólar; otra parte de los costos son insumos locales (alimentos, etc.) que suben con la inflación.
No es una proyección: muestra qué pasaría con tu margen SI el dólar o los insumos se movieran así.
"""
from __future__ import annotations


def margen_resultante(margen_pct: float, ingreso_usd_pct: float, costo_usd_pct: float,
                      var_tc_pct: float = 0.0, costo_insumos_pct: float = 0.0, var_insumos_pct: float = 0.0) -> dict:
    """Todos los parámetros en %. Devuelve el margen nuevo y su cambio en puntos."""
    if not 0 <= margen_pct < 100:
        raise ValueError("El margen debe estar entre 0 y 100")
    for v in (ingreso_usd_pct, costo_usd_pct, costo_insumos_pct):
        if not 0 <= v <= 100:
            raise ValueError("Los porcentajes de estructura deben estar entre 0 y 100")
    if costo_usd_pct + costo_insumos_pct > 100:
        raise ValueError("Costos en dólares + costos en insumos no pueden pasar de 100%")
    t, p = var_tc_pct / 100, var_insumos_pct / 100
    ingreso0, costo0 = 100.0, 100.0 - margen_pct
    ingreso1 = ingreso0 * (1 - ingreso_usd_pct / 100 + ingreso_usd_pct / 100 * (1 + t))
    costo1 = costo0 * ((1 - costo_usd_pct / 100 - costo_insumos_pct / 100)
                       + costo_usd_pct / 100 * (1 + t) + costo_insumos_pct / 100 * (1 + p))
    margen1 = (ingreso1 - costo1) / ingreso1 * 100
    return {"margen_nuevo": margen1, "cambio_pp": margen1 - margen_pct, "ingreso": ingreso1, "costo": costo1}


def grilla_tc(margen_pct: float, ingreso_usd_pct: float, costo_usd_pct: float, costo_insumos_pct: float = 0.0,
              var_insumos_pct: float = 0.0, desde: int = -10, hasta: int = 20, paso: int = 5) -> list[dict]:
    out = []
    for t in range(desde, hasta + 1, paso):
        r = margen_resultante(margen_pct, ingreso_usd_pct, costo_usd_pct, t, costo_insumos_pct, var_insumos_pct)
        out.append({"var_tc_pct": t, "margen_nuevo": r["margen_nuevo"], "cambio_pp": r["cambio_pp"]})
    return out


def tc_que_anula_margen(margen_pct: float, ingreso_usd_pct: float, costo_usd_pct: float,
                        costo_insumos_pct: float = 0.0, var_insumos_pct: float = 0.0) -> float | None:
    """Variación % del dólar con la que el margen llegaría a cero. None si el dólar no lo lleva a cero."""
    costo0 = 100.0 - margen_pct
    p = var_insumos_pct / 100
    base_costo = costo0 * ((1 - costo_usd_pct / 100 - costo_insumos_pct / 100) + costo_usd_pct / 100
                           + costo_insumos_pct / 100 * (1 + p))
    # ingreso(t) = 100 (1 + si t) ; costo(t) = base_costo + costo0 * sc * t
    si, sc = ingreso_usd_pct / 100, costo_usd_pct / 100
    denom = 100 * si - costo0 * sc
    if abs(denom) < 1e-9:
        return None
    t = (base_costo - 100) / denom
    return t * 100 if t > -1 else None
