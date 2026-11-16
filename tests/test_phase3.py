import json
from pathlib import Path
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


# ---------- documentos (RAG) y elección de modelo ----------
from app import docs  # noqa: E402

TEXTO_DOC = ("El Banco Central redujo su proyección de crecimiento para 2026 por el impacto de El Niño extraordinario sobre la pesca y la agricultura. "
             "La inflación podría ubicarse por encima del rango meta hacia fin de año debido a mayores precios de alimentos. ") * 8 + \
            ("La tasa de referencia se mantiene sin cambios mientras se evalúa la evolución de las expectativas. ") * 8


def test_partir_respeta_tamano_y_solape():
    frs = docs.partir(TEXTO_DOC, tam=300, solape=50)
    assert len(frs) > 3 and all(len(f) <= 305 for f in frs)


def test_indexar_y_buscar_con_cita(tmp_path):
    (tmp_path / "reporte_demo.txt").write_text(TEXTO_DOC, encoding="utf-8")
    (tmp_path / "otro.md").write_text("Las exportaciones de harina de pescado dependen de la temporada de anchoveta. " * 10, encoding="utf-8")
    idx = docs.indexar(tmp_path)
    assert set(idx["documentos"]) == {"reporte_demo", "otro"}
    r = docs.buscar("proyección de crecimiento por El Niño", indice=idx)
    assert r and r[0]["fuente"].startswith("reporte_demo, p. ")
    assert docs.buscar("zzzz inexistente", indice=idx) == []


def test_indexar_pdf_con_paginas(tmp_path):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    c = canvas.Canvas(str(tmp_path / "informe.pdf"))
    c.drawString(72, 750, "Pagina uno: el crecimiento de la pesca cayo por El Nino y la anchoveta escaseo en la costa norte del pais durante el primer semestre del ano.")
    c.showPage()
    c.drawString(72, 750, "Pagina dos: la inflacion de alimentos subio por menor oferta agricola luego de las lluvias intensas en la costa norte del Peru este ano.")
    c.save()
    idx = docs.indexar(tmp_path)
    r = docs.buscar("inflacion alimentos lluvias", indice=idx)
    assert r and r[0]["fuente"] == "informe, p. 2"


def test_herramienta_buscar_documentos_y_verificador(tmp_path, monkeypatch):
    (tmp_path / "rep.txt").write_text("El Banco Central proyecta un crecimiento de 3.2% para 2026 por El Niño. " * 8, encoding="utf-8")
    idx = docs.indexar(tmp_path)
    monkeypatch.setattr(docs, "cargar", lambda ruta=docs.INDICE: idx)
    out = chat.ejecutar_herramienta("buscar_documentos", {"consulta": "crecimiento 2026 El Niño"})
    assert out["fragmentos"]
    resultados = [json.dumps(out, ensure_ascii=False)]
    assert chat.cifras_no_respaldadas("El documento proyecta 3.2%.", resultados) == []
    assert chat.cifras_no_respaldadas("El documento proyecta 7.5%.", resultados) == ["7.5"]


def test_buscar_documentos_sin_indice_no_rompe(monkeypatch):
    monkeypatch.setattr(docs, "cargar", lambda ruta=docs.INDICE: {"fragmentos": [], "documentos": {}})
    assert "nota" in chat.ejecutar_herramienta("buscar_documentos", {"consulta": "algo"})


class ClienteConLista:
    def __init__(self, nombres):
        self.models = self
        self._n = nombres

    def list(self):
        return [SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"]) for n in self._n]


def test_elegir_modelo_toma_el_flash_estable_mas_nuevo(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    c = ClienteConLista(["gemini-2.5-flash", "gemini-3.1-flash", "gemini-3.5-flash-preview", "gemini-3.1-flash-lite",
                         "gemini-flash-latest", "gemini-3.1-flash-image", "gemini-2.5-pro"])
    assert chat.elegir_modelo(c) == "gemini-3.1-flash"


def test_elegir_modelo_respeta_variable_y_cae_a_defecto(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "mi-modelo")
    assert chat.elegir_modelo(ClienteConLista([])) == "mi-modelo"
    monkeypatch.delenv("GEMINI_MODEL")
    assert chat.elegir_modelo(SimpleNamespace(models=SimpleNamespace())) == chat.MODELO


# ---------- chat potenciado y noticias ----------
from app import noticia  # noqa: E402


def test_herramientas_nuevas_simular_episodios_plan(datos):
    r = chat.ejecutar_herramienta("simular_margen", {"margen_pct": 20, "ingreso_usd_pct": 0, "costo_usd_pct": 50, "var_tc_pct": 10}, datos)
    assert r["margen_nuevo_pct"] == pytest.approx(16.0)
    e = chat.ejecutar_herramienta("episodios_el_nino", {}, datos)
    assert any(f["variacion_pesca_ene_ago_pct"] < -40 for f in e["episodios"] if f["variacion_pesca_ene_ago_pct"] is not None)
    p = chat.ejecutar_herramienta("plan_exposicion", {"perfil": "Pesca y harina de pescado"}, datos)
    assert p["semaforo_general"] in {"rojo", "amarillo", "verde"} and "aviso" in p
    assert "error" in chat.ejecutar_herramienta("simular_margen", {"margen_pct": 20}, datos)


def test_separar_seguimientos():
    t = "El dólar subió.\n\nFuente: BCRP.\n\nPodrías preguntar:\n- ¿Qué pasa con mis costos?\n- ¿Y la inflación?\n"
    cuerpo, seg = chat.separar_seguimientos(t)
    assert cuerpo.endswith("Fuente: BCRP.") and seg == ["¿Qué pasa con mis costos?", "¿Y la inflación?"]
    assert chat.separar_seguimientos("Solo texto.") == ("Solo texto.", [])


def test_chat_devuelve_trazas_y_seguimientos(datos):
    ult = chat.ejecutar_herramienta("datos_serie", {"id": "ipc_lima", "ultimos": 1}, datos)["observaciones"][0]["valor"]
    out = chat.responder(FalsoCliente(f"El índice está en {ult:.1f}.\n\nPodrías preguntar:\n- ¿Y el dólar?\n- ¿Y el empleo?"),
                         [], "¿precios?", datos, contexto="Tipo de negocio: Importador")
    assert out["trazas"][0]["herramienta"] == "datos_serie" and out["seguimientos"] == ["¿Y el dólar?", "¿Y el empleo?"]
    assert out["advertencias"] == []


def test_cifras_del_usuario_no_se_marcan(datos):
    out = chat.responder(FalsoCliente("Con tu margen de 17.5% el dólar importa."), [], "Mi margen es 17.5%, ¿qué pasa con el dólar?", datos)
    assert out["advertencias"] == []


TEXTO_NOTICIA = ("El BCRP mantuvo su tasa de referencia en 4.25% en su reunión de octubre. La entidad señaló que la inflación a 12 meses "
                 "se ubicaría temporalmente por encima del rango meta por el impacto de El Niño en los precios de los alimentos. "
                 "Analistas esperan que la pesca de anchoveta caiga 30% este año. ")


class ClienteNoticia:
    def __init__(self, datos_json):
        self.models = self
        self.datos = datos_json

    def generate_content(self, model, contents, config):
        assert "<<<TEXTO>>>" in contents and config.response_mime_type == "application/json"
        return SimpleNamespace(text=json.dumps(self.datos, ensure_ascii=False))


ANALISIS_OK = {"resumen_simple": "El Banco Central dejó su tasa en 4.25%. Dice que los precios subirían por El Niño.",
               "terminos": [{"termino": "tasa de referencia", "explicacion": "Es el precio base del dinero que fija el Banco Central."}],
               "cifras": [{"cifra": "30%", "significado": "Los analistas esperan que se pesque 30% menos anchoveta."}],
               "temas": ["tasa_de_interes", "inflacion", "tema_inventado"],
               "por_que_podria_importar": "Si los precios de los alimentos suben, tus costos pueden subir.",
               "lo_que_no_dice": ["No dice cuándo bajará la inflación."]}


def test_noticia_analiza_y_filtra_temas(datos):
    an, malos, recortado = noticia.analizar(ClienteNoticia(ANALISIS_OK), TEXTO_NOTICIA * 2)
    assert malos == [] and not recortado
    assert an.temas == ["tasa_de_interes", "inflacion"]
    rel = noticia.datos_relacionados(an.temas, datos)
    assert {r["id"] for r in rel} >= {"tasa_referencia", "ipc_lima"} and all(r["frases"] for r in rel)


def test_noticia_marca_cifras_que_no_estan_en_el_texto():
    mala = dict(ANALISIS_OK, resumen_simple="El Banco Central subió su tasa a 7.5%.")
    _, malos, _ = noticia.analizar(ClienteNoticia(mala), TEXTO_NOTICIA * 2)
    assert "7.5" in malos


def test_noticia_rechaza_texto_corto_y_recorta_largo():
    with pytest.raises(ValueError):
        noticia.analizar(ClienteNoticia(ANALISIS_OK), "hola")
    _, _, recortado = noticia.analizar(ClienteNoticia(ANALISIS_OK), TEXTO_NOTICIA * 100)
    assert recortado


def test_noticia_leer_archivo_txt():
    assert noticia.leer_archivo("n.txt", "Tasa de 4.25% ñ".encode()) == "Tasa de 4.25% ñ"


def test_app_renderiza_chat_y_noticias_con_clave(datos, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import app.data as d
    monkeypatch.setattr(d, "SERIES_DIR", datos)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-falsa")
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Explicar" == b.label for b in at.button)
    assert any(x.label == "Tipo de negocio" for x in at.selectbox)
