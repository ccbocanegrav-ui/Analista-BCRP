"""Modo rápido del chat (sin API): el código elige las herramientas y Gemini se llama una sola vez."""
from types import SimpleNamespace

from app import chat, rapido


def _nombres(pregunta):
    return [n for n, _ in rapido.elegir_herramientas(pregunta)]


def test_elige_la_serie_del_dolar():
    assert ("resumen_serie", {"id": "tc_interbancario_venta"}) in rapido.elegir_herramientas("¿Cómo está el dólar?")


def test_el_nino_trae_anomalia_y_episodios():
    h = rapido.elegir_herramientas("¿Cómo está El Niño ahora?")
    assert ("anomalia_nino", {}) in h and ("episodios_el_nino", {}) in h


def test_todas_las_series_del_modo_rapido_existen():
    for _, nombre, args in rapido.REGLAS:
        if "id" in args:
            assert "error" not in chat.ejecutar_herramienta(nombre, args), args["id"]


def test_fuera_de_alcance_entrega_el_catalogo():
    assert "listar_series" in _nombres("¿Cuántos turistas llegaron a Cusco en octubre?")


def test_palabras_cortas_no_coinciden_dentro_de_otras():
    assert "exposicion_regional" not in _nombres("Explícame qué pasa con los precios")


def test_preguntas_sobre_documentos_buscan_en_ellos():
    for q in ["¿Qué dice el comunicado del ENFEN?", "¿Qué decidió el BCRP sobre la tasa este mes?",
              "¿Qué dice el programa monetario?", "Según el reporte de inflación, ¿qué pasa con El Niño?"]:
        assert "buscar_documentos" in _nombres(q), q


def test_agroexportadora_de_paita_trae_su_semaforo_y_su_region():
    h = rapido.elegir_herramientas("Soy agroexportadora de uvas, ¿cómo afecta el niño a mi negocio si soy de Paita?")
    assert ("plan_exposicion", {"perfil": rapido.EXPORTADOR}) in h and ("anomalia_nino", {}) in h
    assert ("exposicion_regional", {}) not in h   # el mapa regional es de pesca: no aplica a uvas
    assert ("exposicion_regional", {}) in rapido.elegir_herramientas("Tengo una planta de harina en Paita, ¿me afecta?")


def test_respuesta_con_otro_alfabeto_pasa_al_siguiente_modelo(monkeypatch):
    monkeypatch.setattr(chat, "ejecutar_herramienta", lambda n, a, d=None: {"valor_ultimo": 3.43})
    textos = {"lite": "El dólar sube y تغییر tus costos.", "flash": "El dólar está en S/ 3.43."}
    c = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda model, contents, config: SimpleNamespace(text=textos[model])))
    monkeypatch.setattr(chat, "modelos_lite", lambda cl: ["lite"])
    monkeypatch.setattr(chat, "modelos_candidatos", lambda cl: ["flash"])
    out = rapido.responder(c, [], "¿Cómo está el dólar?")
    assert out["modelo"] == "flash" and "تغییر" not in out["texto"]


def test_modelos_lite_solo_toma_flash_lite_estables():
    m = lambda n: SimpleNamespace(name=f"models/{n}", supported_actions=["generateContent"])  # noqa: E731
    c = SimpleNamespace(models=SimpleNamespace(list=lambda: [m("gemini-3.1-flash-lite"), m("gemini-3.5-flash-lite"),
                                                             m("gemini-3.5-flash-lite-image"), m("gemini-3.6-flash")]))
    assert chat.modelos_lite(c) == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]


def test_cada_sector_recibe_su_semaforo():
    casos = {"Tengo un emprendimiento de postres, ¿cómo me afecta la subida de precios?": rapido.ALIMENTOS,
             "Tengo una cevichería en Piura, ¿cómo me afecta El Niño?": rapido.ALIMENTOS,
             "Compro mercadería en dólares, ¿cómo está el dólar?": rapido.IMPORTADOR,
             "Soy agroexportadora de uvas, ¿cómo me afecta El Niño?": rapido.EXPORTADOR,
             "Tengo una planta de harina de pescado, ¿qué tan expuesta estoy?": rapido.PESCA}
    for q, perfil in casos.items():
        assert ("plan_exposicion", {"perfil": perfil}) in rapido.elegir_herramientas(q), q


def test_harina_de_reposteria_no_es_harina_de_pescado():
    h = rapido.elegir_herramientas("Compré harina y azúcar para mis tortas, ¿van a subir?")
    assert ("resumen_serie", {"id": "harina_precio"}) not in h
    assert ("resumen_serie", {"id": "ipc_alimentos_var"}) in h


def test_margen_va_al_modo_completo():
    assert not rapido.sirve("Mi margen es 20%, ¿qué pasa si sube el dólar?")
    assert rapido.sirve("¿Cómo está el dólar?")


class ClienteUnaLlamada:
    def __init__(self, texto):
        self.llamadas = 0
        self.models = SimpleNamespace(generate_content=self._gen)
        self.texto = texto

    def _gen(self, model, contents, config):
        self.llamadas += 1
        return SimpleNamespace(text=self.texto, function_calls=None)


def test_responde_con_una_sola_llamada_y_verifica_cifras(monkeypatch):
    monkeypatch.setattr(chat, "ejecutar_herramienta", lambda n, a, d=None: {"valor_ultimo": 3.43})
    c = ClienteUnaLlamada("El dólar está en S/ 3.43, no en 9.99.\n\nPodrías preguntar:\n- ¿Y los precios?")
    out = rapido.responder(c, [], "¿Cómo está el dólar?", modelo="m")
    assert c.llamadas == 1
    assert out["advertencias"] == ["9.99"]
    assert out["seguimientos"] == ["¿Y los precios?"]
