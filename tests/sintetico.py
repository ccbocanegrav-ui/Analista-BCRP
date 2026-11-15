"""Datos sintéticos SOLO para pruebas. No representan al Perú real ni se usan en la app publicada."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NINO = {2017: 0.45, 2023: 0.4, 2026: 0.35}   # factor de pesca en años de El Niño


def crear(destino: Path, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    destino.mkdir(parents=True, exist_ok=True)
    cat = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["series"]
    meses = pd.date_range("2012-01-01", "2026-08-01", freq="MS")
    estac = np.array([1.4, 1.5, 1.6, 1.4, 1.0, 0.4, 0.3, 0.6, 0.8, 0.9, 1.0, 0.9])
    pesca_total = np.array([3000 * estac[m.month - 1] * NINO.get(m.year, 1.0) * rng.uniform(0.9, 1.1) for m in meses])
    cuota = {"piura": .15, "la_libertad": .1, "ancash": .3, "lima": .25, "ica": .12}
    for s in cat:
        sid, n = s["id"], len(meses)
        if sid == "tc_interbancario_venta":
            f = pd.date_range("2012-01-02", "2026-11-12", freq="B")
            v = 2.7 + np.cumsum(rng.normal(0.0003, 0.01, len(f))).clip(-0.3, 1.2)
            pd.DataFrame({"fecha": f, "valor": v}).to_csv(destino / f"{sid}.csv", index=False)
            continue
        if sid == "anchoveta_total":
            v = pesca_total
        elif sid.startswith("anchoveta_"):
            v = pesca_total * cuota[sid.replace("anchoveta_", "")]
        elif sid == "ipc_lima":
            v = 100 * 1.003 ** np.arange(n) / 1.003 ** 120
        elif sid == "harina_precio":
            v = 1500 + 40 * np.arange(n) / 10 - 0.25 * (pesca_total - pesca_total.mean()) + rng.normal(0, 40, n)
        elif sid == "harina_export_fob":
            v = 100 + rng.normal(0, 8, n)
        elif sid == "tasa_referencia":
            v = np.full(n, 4.25)
        elif "desempleo" in sid:
            v = 5 + rng.normal(0, .4, n)
        elif sid == "pbi_pesca_yoy":
            v = rng.normal(0, 8, n)
        elif sid == "pbi_pesca_indice":
            v = 80 * estac[meses.month - 1] + rng.normal(0, 3, n)
        elif sid == "ipc_alimentos_var":
            v = rng.normal(0.3, 0.3, n)
        elif sid == "ingreso_formal_real":
            v = 1500 + rng.normal(0, 20, n)
        else:
            v = rng.normal(3, 1.5, n)
        pd.DataFrame({"fecha": meses, "valor": np.asarray(v, dtype=float)}).to_csv(destino / f"{sid}.csv", index=False)
    # anomalía semanal de NOAA (sintética)
    sem = pd.date_range("2012-01-04", "2026-11-04", freq="7D")
    an = np.array([0.1 + (1.8 if d.year in NINO and d.month <= 8 else 0) + rng.normal(0, .3) for d in sem])
    pd.DataFrame({"fecha": sem, "valor": an}).to_csv(destino / "nino12_anomalia.csv", index=False)
