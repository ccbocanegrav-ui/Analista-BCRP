"""Respaldo de modelos y caché del chat (sin API)."""
from types import SimpleNamespace

import pytest

from app import chat


class ErrorCuota(Exception):
    code = 429


def test_con_respaldo_pasa_al_siguiente_modelo_si_se_agota_la_cuota(monkeypatch):
    monkeypatch.setattr(chat, "modelos_candidatos", lambda c: ["a", "b", "c"])
    probados = []

    def funcion(m):
        probados.append(m)
        if m == "a":
            raise ErrorCuota("sin cuota")
        return f"ok-{m}"

    assert chat.con_respaldo(None, funcion) == "ok-b"
    assert probados == ["a", "b"]


def test_con_respaldo_no_oculta_errores_que_no_son_de_cuota(monkeypatch):
    monkeypatch.setattr(chat, "modelos_candidatos", lambda c: ["a", "b"])

    def funcion(m):
        raise ValueError("error de programación")

    with pytest.raises(ValueError):
        chat.con_respaldo(None, funcion)


def test_sin_modelos_da_mensaje_claro(monkeypatch):
    monkeypatch.setattr(chat, "modelos_candidatos", lambda c: ["a", "b"])

    class Retirado(Exception):
        code = 404

    def funcion(m):
        raise ErrorCuota("x") if m == "a" else Retirado("y")

    with pytest.raises(chat.SinModeloDisponible) as e:
        chat.con_respaldo(None, funcion)
    assert "sin cuota por hoy: a" in str(e.value) and "no disponibles: b" in str(e.value)


def test_cache_responde_sin_llamar_a_gemini(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "CACHE_CHAT", tmp_path / "cache.json")
    llamadas = []

    def falso(cliente, historial, pregunta, series_dir, modelo, contexto):
        llamadas.append(modelo)
        return {"texto": "ok", "seguimientos": [], "herramientas": ["datos_serie"], "trazas": [], "advertencias": []}

    monkeypatch.setattr(chat, "_responder_con", falso)
    cliente = SimpleNamespace()
    a = chat.responder(cliente, [], "¿Cómo está el dólar?", modelo="m", usar_cache=True)
    b = chat.responder(cliente, [], "¿cómo está el dólar? ", modelo="m", usar_cache=True)
    assert a == b and len(llamadas) == 1
