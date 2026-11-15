import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.bcrp import load_export_csv, parse_api_json, parse_period
from app.transform import (a_mensual, acumulada_12m_desde_mensual, inflacion_12m,
                           percentil_historico, ultimo_dato, variacion_pct)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("txt,esperado", [
    ("Ene.2020", date(2020, 1, 1)), ("Ene20", date(2020, 1, 1)),
    ("Set.2021", date(2021, 9, 1)), ("Sep26", date(2026, 9, 1)),
    ("02.Ene.20", date(2020, 1, 2)), ("T112", date(2012, 1, 1)),
    ("T3.2019", date(2019, 7, 1)), ("2025", date(2025, 1, 1)),
    ("Dic.1999", date(1999, 12, 1)),
])
def test_parse_period(txt, esperado):
    assert parse_period(txt) == esperado


def test_parse_period_invalido():
    with pytest.raises(ValueError):
        parse_period("hola")


def test_parse_api_json_con_nd():
    payload = {"config": {"series": [{"name": "IPC", "dec": "2"}]},
               "periods": [{"name": "Feb.2026", "values": ["120.5"]},
                           {"name": "Ene.2026", "values": ["n.d."]},
                           {"name": "Mar.2026", "values": ["121.0"]}]}
    df = parse_api_json(payload)
    assert list(df["fecha"].dt.month) == [1, 2, 3]
    assert pd.isna(df["valor"].iloc[0]) and df["valor"].iloc[2] == 121.0


def _indice(n=14, base=100.0, paso=0.01):
    fechas = pd.date_range("2025-01-01", periods=n, freq="MS")
    return pd.DataFrame({"fecha": fechas, "valor": [base * (1 + paso) ** i for i in range(n)]})


def test_inflacion_12m():
    out = inflacion_12m(_indice(14))
    assert len(out) == 2
    assert out["valor"].iloc[0] == pytest.approx(((1.01) ** 12 - 1) * 100)


def test_acumulada_12m_coincide_con_indice():
    idx = _indice(14)
    var_m = pd.DataFrame({"fecha": idx["fecha"].iloc[1:], "valor": [1.0] * 13})
    acum = acumulada_12m_desde_mensual(var_m)
    assert acum["valor"].iloc[0] == pytest.approx(((1.01) ** 12 - 1) * 100)


def test_a_mensual_y_variacion():
    d = pd.DataFrame({"fecha": pd.to_datetime(["2026-01-02", "2026-01-30", "2026-02-02"]),
                      "valor": [3.0, 4.0, 5.0]})
    m = a_mensual(d)
    assert list(m["valor"]) == [3.5, 5.0]
    assert variacion_pct(m, 1) == pytest.approx((5 / 3.5 - 1) * 100)


def test_variacion_sin_datos_suficientes():
    with pytest.raises(ValueError):
        variacion_pct(_indice(3), 12)


def test_percentil_y_ultimo():
    s = pd.DataFrame({"fecha": pd.date_range("2026-01-01", periods=5, freq="MS"), "valor": [1, 2, 3, 4, 5]})
    assert percentil_historico(s, 4) == 80.0
    assert ultimo_dato(s) == {"fecha": "2026-05-01", "valor": 5.0}


def test_load_export_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Fecha,Serie\nEne.2026,1.5\nFeb.2026,n.d.\n")
    df = load_export_csv(p)
    assert len(df) == 2 and df["valor"].iloc[0] == 1.5


def test_catalogo_integridad():
    cat = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["series"]
    ids = [s["id"] for s in cat]
    assert len(ids) == len(set(ids))
    for s in cat:
        assert re.fullmatch(r"[A-Z]{2}\d{5}[A-Z]{2}", s["code"]), s["code"]
        assert isinstance(s["verificada"], bool)
        assert s["frecuencia"] in {"diaria", "mensual", "trimestral", "anual"}
