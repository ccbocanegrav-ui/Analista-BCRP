"""Modo rápido del chat: 1 sola llamada a Gemini por pregunta.

En el modo normal, Gemini decide qué herramientas usar y eso cuesta ~4 llamadas por pregunta.
Aquí el código elige las herramientas por palabras clave (sin IA), las ejecuta y le entrega
los resultados a Gemini, que solo redacta. Gasta ~4 veces menos cuota y responde más rápido.
El verificador de cifras funciona igual: revisa que cada número esté en los datos entregados.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from app import chat, indicators

PERFILES = list(indicators.PERFILES)
IMPORTADOR, ALIMENTOS, EXPORTADOR, PESCA = PERFILES[:4]

# (palabras clave, herramienta, argumentos). Las palabras se buscan sin tildes y en minúsculas.
REGLAS: list[tuple[tuple[str, ...], str, dict]] = [
    (("dolar", "tipo de cambio", "divisa"), "resumen_serie", {"id": "tc_interbancario_venta"}),
    (("alimento", "comida", "canasta"), "resumen_serie", {"id": "ipc_alimentos_var"}),
    (("precio", "inflacion", "ipc", "caro", "costo de vida"), "resumen_serie", {"id": "ipc_lima"}),
    (("tasa", "interes", "credito", "prestamo"), "resumen_serie", {"id": "tasa_referencia"}),
    (("pbi", "economia", "crecimiento", "crece", "actividad"), "resumen_serie", {"id": "pbi_mensual_yoy"}),
    (("pecuario", "pollo", "carne", "ganado", "huevo", "leche"), "resumen_serie", {"id": "pbi_pecuario_yoy"}),
    (("joven", "jovenes"), "resumen_serie", {"id": "desempleo_lima_14_24"}),
    (("empleo", "desempleo", "trabajo"), "resumen_serie", {"id": "desempleo_lima"}),
    (("ingreso", "sueldo", "salario"), "resumen_serie", {"id": "ingreso_formal_real"}),
    (("nino", "clima", "mar ", "calentamiento", "anomalia", "enfen", "noaa", "temperatura"), "anomalia_nino", {}),
    (("nino", "episodio", "anchoveta", "pesca"), "episodios_el_nino", {}),
    (("anchoveta", "pesca", "pesquer"), "resumen_serie", {"id": "anchoveta_total"}),
    (("region", "piura", "ancash", "libertad", "ica", "mapa"), "exposicion_regional", {}),
    (("harina",), "resumen_serie", {"id": "harina_precio"}),
]
PERFIL_CLAVES = [
    (("harina", "pesca", "pesquer", "anchoveta"), PESCA),
    (("importo", "importador", "importa", "mercaderia", "insumos"), IMPORTADOR),
    (("exporto", "exportador", "exporta"), EXPORTADOR),
    (("bodega", "restaurante", "pollo", "comida", "alimento", "tienda", "brasa"), ALIMENTOS),
]
DOCUMENTOS = ("reporte", "documento", "bcrp dice", "segun el bcrp", "proyeccion", "proyecta", "espera", "por que", "causa")
NEGOCIO = ("expuest", "riesgo", "semaforo", "mi negocio", "tengo un", "tengo una", "que hago", "plan", "afecta")
MAX_HERRAMIENTAS = 5

SISTEMA_RAPIDO = chat.SISTEMA.replace("tus herramientas", "la sección DATOS").replace("una herramienta", "la sección DATOS") + """

MODO RÁPIDO: ya consultamos los datos por ti; están abajo en DATOS (en JSON). No tienes herramientas.
Responde SOLO con esos datos. Si no alcanzan para responder, dilo y sugiere qué sí puedes contar (las series del catálogo)."""


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _hay(claves, q: str) -> bool:
    """¿Alguna clave aparece al inicio de una palabra? (evita que 'ica' coincida dentro de 'explícame')."""
    return any(re.search(r"\b" + re.escape(c), q) for c in claves)


def elegir_herramientas(pregunta: str, historial: list[dict] | None = None) -> list[tuple[str, dict]]:
    """Herramientas a ejecutar según las palabras de la pregunta (y del último mensaje del usuario, para seguimientos)."""
    previo = [m["content"] for m in (historial or []) if m["role"] == "user"][-1:]
    q = _normalizar(" ".join(previo + [pregunta])) + " "
    elegidas: list[tuple[str, dict]] = []

    def agregar(nombre, args):
        if (nombre, args) not in elegidas:
            elegidas.append((nombre, args))

    perfil = next((p for claves, p in PERFIL_CLAVES if _hay(claves, q)), None)
    if perfil and _hay(NEGOCIO, q):
        agregar("plan_exposicion", {"perfil": perfil})
    for claves, nombre, args in REGLAS:
        if _hay(claves, q):
            agregar(nombre, args)
    if _hay(DOCUMENTOS, q):
        agregar("buscar_documentos", {"consulta": pregunta})
    if q.strip(" ¿¡").startswith(("que es", "que significa", "como funciona")) or not elegidas:
        agregar("buscar_fichas", {"consulta": pregunta})
    if not elegidas or elegidas == [("buscar_fichas", {"consulta": pregunta})]:
        agregar("listar_series", {})   # para que pueda decir qué sí cubre
    return elegidas[:MAX_HERRAMIENTAS]


def sirve(pregunta: str, contexto: str = "") -> bool:
    """El modo rápido no simula márgenes (eso necesita que el modelo arme los parámetros): esas van al modo completo."""
    return not _hay(("margen", "simula"), _normalizar(pregunta + " " + contexto))


def responder(cliente, historial: list[dict], pregunta: str, series_dir: Path | None = None,
              modelo: str | None = None, contexto: str = "") -> dict:
    """Misma salida que chat.responder, pero con una sola llamada a Gemini."""
    from google.genai import types
    trazas, resultados = [], []
    for nombre, args in elegir_herramientas(pregunta, historial):
        salida = chat.ejecutar_herramienta(nombre, args, series_dir)
        txt = json.dumps(salida, ensure_ascii=False, default=str)
        resultados.append(txt)
        trazas.append({"herramienta": nombre, "args": args, "resultado": json.loads(txt)})
    datos = "\n".join(f"[{t['herramienta']}] {r}" for t, r in zip(trazas, resultados))
    sistema = SISTEMA_RAPIDO + (f"\n\nCONTEXTO DEL USUARIO (datos que él declaró):\n{contexto}" if contexto else "")
    config = types.GenerateContentConfig(system_instruction=sistema, max_output_tokens=1500,
                                         http_options=types.HttpOptions(timeout=45_000))
    contenidos = chat._contenido(historial, f"{pregunta}\n\nDATOS:\n{datos}")

    def llamar(m):
        resp = chat._generar(cliente, m, contenidos, config)
        return m, (resp.text or "").strip()

    usado, texto = chat.con_respaldo(cliente, llamar, modelo)
    cuerpo, seguimientos = chat.separar_seguimientos(texto)
    return {"texto": cuerpo, "seguimientos": seguimientos, "herramientas": [t["herramienta"] for t in trazas],
            "trazas": trazas, "modelo": usado,
            "advertencias": chat.cifras_no_respaldadas(cuerpo, resultados + [contexto, pregunta])}
