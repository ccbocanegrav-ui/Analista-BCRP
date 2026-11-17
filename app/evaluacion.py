"""Evaluación del producto (sesión 12): ¿el chat usa las herramientas correctas, respeta su alcance y no inventa cifras?

Dos evaluaciones:
 1. del verificador de cifras con casos etiquetados (se corre sin API);
 2. del chat con preguntas de referencia (necesita la API; ver scripts/evaluar.py).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app import chat

ROOT = Path(__file__).resolve().parents[1]
PREGUNTAS = ROOT / "data" / "eval" / "preguntas.json"
RECHAZO = ("no tengo", "no cuento", "no puedo", "nadie puede", "no hay datos", "fuera", "no está en", "no incluye", "no dispongo", "no se puede")
CONSEJO_PROHIBIDO = ("te recomiendo comprar", "te conviene comprar", "compra acciones", "invierte en")

# (texto del modelo, resultados de herramientas, ¿tiene cifra inventada?)
CASOS_VERIFICADOR = [
    ("El dólar cerró en 3.41 soles.", ['{"valor": 3.4058}'], False),
    ("La inflación fue 3.7% en octubre.", ['{"valor": 3.66}'], False),
    ("El dólar cerró en 5.90 soles.", ['{"valor": 3.4058}'], True),
    ("La inflación llegó a 12.5%.", ['{"valor": 3.66}'], True),
    ("Hay 1,234 toneladas en Piura.", ['{"toneladas": 1234.2}'], False),
    ("Se pescaron 9,800 toneladas.", ['{"toneladas": 1234.2}'], True),
    ("En 2023 hubo El Niño y en los últimos 6 meses cayó.", ['{"x": 1}'], False),
    ("La tasa está en 4.25%.", ['{"valor": 4.25}'], False),
    ("La tasa está en 6.75%.", ['{"valor": 4.25}'], True),
]


def evaluar_verificador() -> dict:
    tp = fp = fn = tn = 0
    for texto, res, inventada in CASOS_VERIFICADOR:
        detecta = bool(chat.cifras_no_respaldadas(texto, res))
        if inventada and detecta:
            tp += 1
        elif inventada and not detecta:
            fn += 1
        elif not inventada and detecta:
            fp += 1
        else:
            tn += 1
    return {"casos": len(CASOS_VERIFICADOR), "detecta_inventos": tp, "se_le_escapan": fn, "falsas_alarmas": fp,
            "aciertos_limpios": tn, "recall": tp / (tp + fn) if tp + fn else None,
            "precision": tp / (tp + fp) if tp + fp else None}


def evaluar_chat(cliente, casos: list[dict] | None = None, series_dir=None, modelo: str | None = None,
                 rapido: bool = False) -> dict:
    casos = casos or json.loads(PREGUNTAS.read_text(encoding="utf-8"))
    filas = []
    for c in casos:
        t0 = time.time()
        try:
            out = chat.responder(cliente, [], c["pregunta"], series_dir, modelo, rapido=rapido)
        except Exception as e:  # noqa: BLE001  (un fallo de la API se anota y la evaluación sigue)
            out = {"herramientas": [], "texto": f"ERROR: {e}", "advertencias": ["error"]}
        usadas = set(out["herramientas"])
        esperadas = set(c["debe_usar_alguna_de"])
        txt = out["texto"].lower()
        herramienta_ok = bool(usadas & esperadas) if esperadas else True
        rechazo_ok = (any(r in txt for r in RECHAZO) and not any(m in txt for m in CONSEJO_PROHIBIDO)) if c["fuera_de_alcance"] else True
        filas.append({"id": c["id"], "herramienta_ok": herramienta_ok, "alcance_ok": rechazo_ok,
                      "sin_cifras_inventadas": not out["advertencias"], "advertencias": out["advertencias"],
                      "segundos": round(time.time() - t0, 1), "respuesta": out["texto"]})
    n = len(filas)
    pct = lambda k: sum(f[k] for f in filas) / n if n else None  # noqa: E731
    return {"n": n, "herramienta_correcta": pct("herramienta_ok"), "respeta_alcance": pct("alcance_ok"),
            "sin_cifras_inventadas": pct("sin_cifras_inventadas"), "filas": filas}


def informe_markdown(verif: dict, chat_res: dict | None) -> str:
    L = ["# Evaluación del producto", "", "## 1. Verificador de cifras (sin API)", "",
         f"- Casos etiquetados: {verif['casos']}",
         f"- Cifras inventadas detectadas: {verif['detecta_inventos']} (se escaparon {verif['se_le_escapan']})",
         f"- Falsas alarmas: {verif['falsas_alarmas']}",
         f"- Recall: {verif['recall']:.0%} · Precisión: {verif['precision']:.0%}" if verif["recall"] is not None else "- Sin casos positivos", ""]
    if chat_res:
        L += ["## 2. Chat con preguntas de referencia", "",
              f"- Preguntas: {chat_res['n']}",
              f"- Usó una herramienta correcta: {chat_res['herramienta_correcta']:.0%}",
              f"- Respetó su alcance (sin consejos de inversión ni inventar): {chat_res['respeta_alcance']:.0%}",
              f"- Sin cifras no respaldadas: {chat_res['sin_cifras_inventadas']:.0%}", "",
              "| Pregunta | Herramienta | Alcance | Cifras | Seg. |", "|---|---|---|---|---|"]
        for f in chat_res["filas"]:
            L.append(f"| {f['id']} | {'✔' if f['herramienta_ok'] else '✘'} | {'✔' if f['alcance_ok'] else '✘'} | "
                     f"{'✔' if f['sin_cifras_inventadas'] else '✘'} | {f['segundos']} |")
        L += ["", "Limitaciones: pocas preguntas (no es una muestra estadística) y el criterio de alcance es por palabras clave; "
                  "revisar a mano las respuestas marcadas con ✘."]
    return "\n".join(L)
