"""Descarga la anomalía semanal de temperatura del mar (Niño 1+2) del NOAA/CPC y la guarda como CSV.

Uso:
    python scripts/fetch_noaa.py                       # descarga el archivo semanal del CPC
    python scripts/fetch_noaa.py --from-file wksst.txt  # si lo descargaste a mano desde tu navegador

El archivo semanal (wksst9120.for) tiene una fila por semana: fecha (p. ej. 03JAN1990) y luego, para cada región
(Niño 1+2, 3, 3.4, 4), la temperatura y su anomalía. Se toma la anomalía de Niño 1+2 (segundo número).
REVISA las primeras filas del CSV generado contra el archivo original antes de confiar en él.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
SALIDA = ROOT / "data" / "series" / "nino12_anomalia.csv"
MESES = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
FILA = re.compile(r"^\s*(\d{2})([A-Z]{3})(\d{4})(.*)$")
NUM = re.compile(r"-?\d+\.\d+")


def parsear(texto: str) -> pd.DataFrame:
    """Convierte el texto del CPC en DataFrame(fecha, valor) con la anomalía Niño 1+2."""
    filas = []
    for linea in texto.splitlines():
        m = FILA.match(linea)
        if not m or m.group(2) not in MESES:
            continue
        nums = NUM.findall(m.group(4))   # los números pueden venir pegados: 23.4-0.4
        if len(nums) < 2:
            continue
        fecha = pd.Timestamp(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
        filas.append({"fecha": fecha, "valor": float(nums[1])})
    if not filas:
        raise ValueError("No se reconoció ninguna fila. Revisa el formato del archivo.")
    return pd.DataFrame(filas).sort_values("fecha").reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file")
    args = ap.parse_args()
    if args.from_file:
        texto = Path(args.from_file).read_text(encoding="utf-8", errors="ignore")
    else:
        import requests
        r = requests.get(URL, timeout=60, headers={"User-Agent": "TermometroBCRP/0.1 (proyecto academico UP)"})
        r.raise_for_status()
        texto = r.text
    df = parsear(texto)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SALIDA, index=False)
    print(f"{len(df)} semanas guardadas en {SALIDA}")
    print("Primeras filas:\n", df.head(3).to_string(index=False))
    print("Últimas filas:\n", df.tail(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
