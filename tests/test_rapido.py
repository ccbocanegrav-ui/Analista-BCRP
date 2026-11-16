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
