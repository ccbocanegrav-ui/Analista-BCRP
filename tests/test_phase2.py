import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import periodista
from app.indicators import PERFILES, evaluar, evaluar_indicador
from app.transform import acumulado_interanual, serie_variacion


def guardar(dir: Path, sid: str, valores, freq="MS", inicio="2019-01-01"):
    fechas = pd.date_range(inicio, periods=len(valores), freq=freq)
    pd.DataFrame({"fecha": fechas, "valor": valores}).to_csv(dir / f"{sid}.csv", index=False)


def tc_sube(n=60):
    return [3.5] * (n - 12) + list(np.linspace(3.5, 4.4, 12))


def tc_baja(n=60):
    return [3.5] * (n - 12) + list(np.linspace(3.5, 2.9, 12))


def test_serie_variacion_y_acumulado():
    d = pd.DataFrame({"fecha": pd.date_range("2024-01-01", periods=24, freq="MS"), "valor": [100.0] * 12 + [110.0] * 12})
    assert serie_variacion(d, 12)["valor"].iloc[-1] == pytest.approx(10.0)
    assert acumulado_interanual(d, 6)["valor"].iloc[-1] == pytest.approx(10.0)


def test_semaforo_importador_rojo_si_dolar_sube(tmp_path):
    guardar(tmp_path, "tc_interbancario_prom_mensual", tc_sube())
    ind = evaluar_indicador("tc_var12", "alza", tmp_path)
    assert ind.color == "rojo"


def test_semaforo_importador_verde_si_dolar_baja(tmp_path):
    guardar(tmp_path, "tc_interbancario_prom_mensual", tc_baja())
    assert evaluar_indicador("tc_var12", "alza", tmp_path).color == "verde"


def test_exportador_rojo_si_dolar_baja(tmp_path):
    guardar(tmp_path, "tc_interbancario_prom_mensual", tc_baja())
    assert evaluar_indicador("tc_var12", "baja", tmp_path).color == "rojo"


def test_sin_datos_es_gris_y_no_rompe(tmp_path):
    res = evaluar("Pesca y harina de pescado", tmp_path)
    assert res["general"] == "gris"
    assert all(i["color"] == "gris" for i in res["indicadores"])


def test_evaluar_todos_los_perfiles_con_datos_sinteticos(tmp_path):
    n = 60
    guardar(tmp_path, "tc_interbancario_prom_mensual", tc_sube())
    guardar(tmp_path, "ipc_lima", [100 * 1.003 ** i for i in range(n)])
    guardar(tmp_path, "pbi_mensual_yoy", [3.0] * (n - 3) + [-2.0, -3.0, -4.0])
    guardar(tmp_path, "harina_precio", [1500.0] * (n - 12) + list(np.linspace(1500, 900, 12)))
    guardar(tmp_path, "anchoveta_total", [1000.0] * (n - 12) + [200.0] * 12)
    guardar(tmp_path, "pbi_pesca_yoy", [1.0] * (n - 3) + [-20.0, -25.0, -30.0])
    for perfil in PERFILES:
        res = evaluar(perfil, tmp_path)
        assert res["general"] in {"rojo", "amarillo", "verde"}
        assert res["advertencia"]
    assert evaluar("Pesca y harina de pescado", tmp_path)["general"] == "rojo"


def test_periodista_plantilla_se_verifica_y_detecta_inventos(tmp_path):
    n = 40
    guardar(tmp_path, "tc_interbancario_venta", list(np.linspace(3.3, 3.45, 900)), freq="D", inicio="2024-06-01")
    guardar(tmp_path, "ipc_lima", [100 * 1.003 ** i for i in range(n)])
    guardar(tmp_path, "tasa_referencia", [4.25] * n)
    guardar(tmp_path, "pbi_mensual_yoy", [3.2] * n)
    hs = periodista.hechos(tmp_path)
    assert len(hs) == 4
    nota = periodista.nota_plantilla(hs)
    assert periodista.verificar_numeros(nota, hs) == []
    inventada = nota + " Además el dólar llegó a 5,90 soles."
    assert "5,90" in periodista.verificar_numeros(inventada, hs)


def test_periodista_omite_hechos_sin_datos(tmp_path):
    assert periodista.hechos(tmp_path) == []
    assert "No hay datos" in periodista.nota_plantilla([])
