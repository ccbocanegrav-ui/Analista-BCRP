"""Descarga las series del catálogo desde BCRPData y las guarda en data/series/*.csv.

Uso:
    python scripts/fetch_bcrp.py --check            # una sola serie para probar el formato
    python scripts/fetch_bcrp.py                    # todas las del catálogo
    python scripts/fetch_bcrp.py --only ipc_lima    # una por id
    python scripts/fetch_bcrp.py --from-csv ipc_lima ruta/export.csv   # plan B manual
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.bcrp import fetch_series, load_export_csv, save_series  # noqa: E402

CATALOGO = ROOT / "data" / "catalog.json"
SERIES_DIR = ROOT / "data" / "series"
USER_AGENT = "TermometroBCRP/0.1 (proyecto academico UP)"


def formato_fecha(frecuencia: str, d: date) -> str:
    return f"{d.year}-{d.month}-{d.day}" if frecuencia == "diaria" else f"{d.year}-{d.month}"


def cargar_catalogo() -> list[dict]:
    return json.loads(CATALOGO.read_text(encoding="utf-8"))["series"]


def run(only: str | None, check: bool, desde_anio: int, delay: float) -> int:
    series = cargar_catalogo()
    if check:
        series = [s for s in series if s["id"] == "ipc_lima"]
    elif only:
        series = [s for s in series if s["id"] == only]
    if not series:
        print("No hay series que descargar (revisa --only).")
        return 1

    sesion = requests.Session()
    sesion.headers["User-Agent"] = USER_AGENT
    hoy = date.today()
    fallas = 0
    for s in series:
        desde = formato_fecha(s["frecuencia"], date(desde_anio, 1, 1))
        hasta = formato_fecha(s["frecuencia"], hoy)
        try:
            df = fetch_series(sesion, s["code"], desde, hasta)
        except Exception as e:
            print(f"FALLÓ {s['id']} ({s['code']}): {e}")
            fallas += 1
            continue
        if df.empty or df["valor"].notna().sum() == 0:
            print(f"VACÍA {s['id']} ({s['code']}): revisa el código o el rango")
            fallas += 1
            continue
        save_series(df, SERIES_DIR / f"{s['id']}.csv")
        u = df.dropna().iloc[-1]
        marca = "" if s.get("verificada") else "  [código SIN verificar]"
        print(f"ok  {s['id']:<28} {len(df):>5} obs  último: {u['fecha'].date()} = {u['valor']}{marca}")
        time.sleep(delay)
    print(f"\nListo. Fallas: {fallas}")
    return 0 if fallas == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only")
    ap.add_argument("--check", action="store_true", help="prueba con una sola serie")
    ap.add_argument("--desde", type=int, default=2012, help="año inicial")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--from-csv", nargs=2, metavar=("ID", "CSV"))
    a = ap.parse_args()
    if a.from_csv:
        sid, ruta = a.from_csv
        save_series(load_export_csv(Path(ruta)), SERIES_DIR / f"{sid}.csv")
        print(f"Guardado data/series/{sid}.csv")
        return 0
    return run(a.only, a.check, a.desde, a.delay)


if __name__ == "__main__":
    sys.exit(main())
