import json
from types import SimpleNamespace

import pandas as pd
import pytest

from app import chat, geo, narrativa, negocio, nino, plan
from app.indicators import evaluar
from scripts.fetch_noaa import parsear
from tests.sintetico import crear


@pytest.fixture(scope="module")
def datos(tmp_path_factory):
    d = tmp_path_factory.mktemp("sint")
    crear(d)
    return d


# ---------- narrativa ----------
def test_resumen_nivel_calcula_cambio_y_frases(datos):
    r = narrativa.resumen("harina_precio", datos)
    assert "cambio6" in r and "cambio12" in r
    assert any("6 meses" in f for f in r["frases"])
    assert any("último año" in f for f in r["frases"])


def test_resumen_tasa_usa_puntos(datos):
    r = narrativa.resumen("pbi_mensual_yoy", datos)
    assert any("puntos" in f for f in r["frases"])


def test_resumen_estacional_compara_con_mismo_periodo(datos):
    r = narrativa.resumen("anchoveta_total", datos)
    assert any("mismo período del año anterior" in f for f in r["frases"])


def test_resumen_inflacion_desde_indice(datos):
    r = narrativa.resumen("ipc_lima", datos)
    assert r["valor_ultimo"] == pytest.approx(3.66, abs=0.1)  # 1.003^12 − 1


def test_todas_las_series_se_resumen_sin_romper(datos):
    from app.data import catalogo
    for s in catalogo():
        if (datos / f"{s['id']}.csv").exists():
            assert narrativa.texto(s["id"], datos)


def test_texto_sin_datos_no_rompe(tmp_path):
    assert "no hay datos" in narrativa.texto("ipc_lima", tmp_path).lower()


# ---------- geo ----------
def test_tabla_regional_participacion_suma_100(datos):
    t = geo.tabla_regional(datos)
    assert len(t) == 5
    assert t["participacion_pct"].sum() == pytest.approx(100)
    assert (t["caida_promedio_episodios"] <= 0).all()
    assert t.attrs["cobertura_pct"] == pytest.approx(92, abs=3)


def test_caida_en_episodio_detecta_el_nino(datos):
    assert geo.caida_en_episodio("anchoveta_total", 2023, datos) < -40


def test_escenario_es_proporcional(datos):
    t = geo.tabla_regional(datos)
    e = geo.escenario(t, 20)
    assert e["toneladas_perdidas"].sum() == pytest.approx(t["toneladas_12m"].sum() * 0.2)


def test_sensibilidad_harina_pendiente_negativa(datos):
    s = geo.sensibilidad_precio_harina(datos)
    assert s is not None and s["pendiente"] < 0 and 0 <= s["r2"] <= 1


def test_sensibilidad_sin_datos_es_none(tmp_path):
    assert geo.sensibilidad_precio_harina(tmp_path) is None


# ---------- negocio ----------
def test_sin_exposicion_el_margen_no_cambia():
    r = negocio.margen_resultante(20, 0, 0, var_tc_pct=15)
    assert r["cambio_pp"] == pytest.approx(0)


def test_dolar_sube_reduce_margen_si_costos_en_dolares():
    r = negocio.margen_resultante(20, 0, 50, var_tc_pct=10)
    # costos 80 -> 80*(0.5+0.5*1.1)=84 ; ingreso 100 ; margen 16
    assert r["margen_nuevo"] == pytest.approx(16)


def test_exportador_gana_si_dolar_sube():
    assert negocio.margen_resultante(20, 100, 0, var_tc_pct=10)["margen_nuevo"] > 20


def test_equilibrio_tc_coincide_con_margen_cero():
    t = negocio.tc_que_anula_margen(10, 0, 60)
    r = negocio.margen_resultante(10, 0, 60, var_tc_pct=t)
    assert r["margen_nuevo"] == pytest.approx(0, abs=1e-6)


def test_equilibrio_none_si_no_hay_exposicion():
    assert negocio.tc_que_anula_margen(10, 0, 0) is None


def test_insumos_suben_reducen_margen():
    r = negocio.margen_resultante(15, 0, 0, 0, costo_insumos_pct=60, var_insumos_pct=10)
    assert r["cambio_pp"] < 0


@pytest.mark.parametrize("args", [(120, 0, 0), (10, 0, 70, 0, 50), (10, 150, 0)])
def test_parametros_invalidos(args):
    with pytest.raises(ValueError):
        negocio.margen_resultante(*args)


# ---------- plan ----------
def test_plan_tiene_horizontes_y_aviso(datos):
    res = evaluar("Pesca y harina de pescado", datos)
    p = plan.construir(res)
    assert set(p["acciones"]) == {"Esta semana", "Próximos 3 meses", "Si empeora"}
    assert "no son una recomendación" in p["aviso"]
    assert all(v["umbral_rojo"] is not None for v in p["vigilar"])


def test_umbral_rojo_es_consistente_con_el_color(datos):
    res = evaluar("Importador (insumos o mercadería en dólares)", datos)
    for i in res["indicadores"]:
        if i["color"] == "rojo" and i["sentido"] == "alza":
            assert i["valor"] >= i["umbral_rojo"] - 1e-9


# ---------- NOAA ----------
MUESTRA = """ Weekly SST data starts on 3 Jan 1990
       Nino1+2      Nino3        Nino34        Nino4
 Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA
 03JAN1990     23.4-0.4     25.1-0.3     26.6 0.0     28.6 0.3
 10JAN1990     23.4-0.8     25.2-0.3     26.6 0.1     28.6 0.3
 17JAN1990     24.5 1.2     25.2-0.2     26.5 0.0     28.6 0.3
"""


def test_parser_noaa_toma_anomalia_nino12():
    d = parsear(MUESTRA)
    assert list(d["valor"]) == [-0.4, -0.8, 1.2]
    assert d["fecha"].iloc[0] == pd.Timestamp("1990-01-03")


def test_parser_noaa_falla_con_formato_desconocido():
    with pytest.raises(ValueError):
        parsear("nada que ver")


def test_anomalia_mensual_y_correlacion_negativa(datos):
    a = nino.anomalia_mensual(datos)
    assert a is not None
    c = nino.correlacion_con_pesca(a, geo.cargar(geo.TOTAL, datos))
    assert c is not None and c["r"] < 0


# ---------- chat ----------
def test_herramienta_fuera_del_catalogo_no_rompe(datos):
    assert "error" in chat.ejecutar_herramienta("resumen_serie", {"id": "inventada"}, datos)
    assert "error" in chat.ejecutar_herramienta("herramienta_falsa", {}, datos)


def test_herramientas_devuelven_datos(datos):
    r = chat.ejecutar_herramienta("datos_serie", {"id": "ipc_lima", "ultimos": 3}, datos)
    assert len(r["observaciones"]) == 3
    assert chat.ejecutar_herramienta("exposicion_regional", {}, datos)["regiones"]
    assert chat.ejecutar_herramienta("buscar_fichas", {"consulta": "dólar tipo de cambio"}, datos)["fichas"]


def test_verificador_detecta_cifra_inventada():
    res = [json.dumps({"valor": 3.4058, "texto": "dólar a 3.41"})]
    assert chat.cifras_no_respaldadas("El dólar está en 3.41 soles.", res) == []
    assert chat.cifras_no_respaldadas("El dólar está en 5.90 soles.", res) == ["5.90"]
    assert chat.cifras_no_respaldadas("En 2026 y 6 meses, sin cifras.", res) == []


class FalsoCliente:
    """Simula Gemini: primero pide una herramienta (function call) y luego responde con texto."""

    def __init__(self, respuesta_final):
        self.llamadas = 0
        self.final = respuesta_final
        self.models = self
        self.recibidos = []

    def generate_content(self, model, contents, config):
        self.llamadas += 1
        self.recibidos.append(contents)
        if self.llamadas == 1:
            llamada = SimpleNamespace(name="datos_serie", args={"id": "ipc_lima", "ultimos": 2})
            return SimpleNamespace(function_calls=[llamada], text=None,
                                   candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[]))])
        return SimpleNamespace(function_calls=None, text=self.final, candidates=[])


def test_ciclo_de_chat_usa_herramienta_y_verifica(datos):
    ult = chat.ejecutar_herramienta("datos_serie", {"id": "ipc_lima", "ultimos": 1}, datos)["observaciones"][0]["valor"]
    ok = chat.responder(FalsoCliente(f"El índice está en {ult:.1f}."), [], "¿precios?", datos)
    assert ok["herramientas"] == ["datos_serie"] and ok["advertencias"] == []
    mal = chat.responder(FalsoCliente("La inflación es 87.3%."), [], "¿precios?", datos)
    assert "87.3" in mal["advertencias"]


# ---------- salidas estructuradas, voz y evaluación ----------
from app import estructurado, evaluacion, periodista, voz  # noqa: E402


class ClienteNota:
    def __init__(self, entrada):
        self.models = self
        self.entrada = entrada

    def generate_content(self, model, contents, config):
        assert config.response_mime_type == "application/json"
        return SimpleNamespace(text=json.dumps(self.entrada, ensure_ascii=False))


def test_nota_estructurada_valida_y_verifica(datos):
    hs = periodista.hechos(datos)
    assert hs
    h = hs[1]
    ok = {"titular": "La inflación sigue controlada", "bajada": h["texto"],
          "puntos": [{"texto": h["texto"], "cifra": h["valores"][0], "serie": h["fuente"]}], "fuente": "BCRPData"}
    nota, malos = estructurado.generar(ClienteNota(ok), hs)
    assert malos == [] and nota.puntos[0].serie == h["fuente"]
    assert "La inflación" in estructurado.a_texto(nota)


def test_nota_estructurada_detecta_cifra_inventada(datos):
    hs = periodista.hechos(datos)
    mala = {"titular": "Dólar a 9.99 soles", "bajada": "Todo se dispara", "fuente": "BCRPData",
            "puntos": [{"texto": "El dólar llegó a 9.99", "cifra": 9.99, "serie": "PD04638PD"}]}
    _, malos = estructurado.generar(ClienteNota(mala), hs)
    assert "9.99" in malos


def test_nota_estructurada_rechaza_esquema_invalido(datos):
    with pytest.raises(Exception):
        estructurado.generar(ClienteNota({"titular": "x"}), periodista.hechos(datos))


def test_voz_limpia_texto_y_falla_con_mensaje(monkeypatch):
    assert voz.limpiar("**Dólar** a S/ 3.4 (+2%)") == "Dólar a soles 3.4 (+2 por ciento)"
    with pytest.raises(RuntimeError):
        voz.sintetizar("   ")


def test_voz_con_servicio_simulado(monkeypatch):
    import sys, types
    class FalsoGTTS:
        def __init__(self, texto, lang): self.texto = texto
        def write_to_fp(self, fp): fp.write(b"MP3:" + self.texto.encode())
    monkeypatch.setitem(sys.modules, "gtts", types.SimpleNamespace(gTTS=FalsoGTTS))
    assert voz.sintetizar("Hola mundo").startswith(b"MP3:")


def test_evaluacion_del_verificador_es_buena():
    v = evaluacion.evaluar_verificador()
    assert v["recall"] == 1.0 and v["falsas_alarmas"] == 0


def test_evaluacion_del_chat_con_cliente_falso(datos):
    casos = [{"id": "x", "pregunta": "¿precios?", "debe_usar_alguna_de": ["datos_serie"], "fuera_de_alcance": False}]
    ult = chat.ejecutar_herramienta("datos_serie", {"id": "ipc_lima", "ultimos": 1}, datos)["observaciones"][0]["valor"]
    r = evaluacion.evaluar_chat(FalsoCliente(f"El índice está en {ult:.1f}."), casos, datos)
    assert r["herramienta_correcta"] == 1.0 and r["sin_cifras_inventadas"] == 1.0
    assert "Evaluación" in evaluacion.informe_markdown(evaluacion.evaluar_verificador(), r)


def test_historial_se_convierte_a_roles_de_gemini(datos):
    c = FalsoCliente("Sin cifras.")
    chat.responder(c, [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡hola!"}], "¿precios?", datos)
    roles = [m.role for m in c.recibidos[0]]
    assert roles[:3] == ["user", "model", "user"]


def test_declaraciones_de_herramientas_son_validas():
    tools = chat._declaraciones()
    nombres = [f.name for f in tools[0].function_declarations]
    assert set(nombres) == {h["name"] for h in chat.HERRAMIENTAS}


def test_esquema_de_nota_es_compatible_con_gemini():
    esq = estructurado.NotaPeriodistica.model_json_schema()
    assert "maxLength" not in json.dumps(esq) and "minItems" not in json.dumps(esq)
