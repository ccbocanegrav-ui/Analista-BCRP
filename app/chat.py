"""Chat analista (Gemini): el modelo solo puede consultar las series del catálogo mediante herramientas.

Los números los entregan las herramientas (código); el modelo los explica en lenguaje simple.
Después de responder, un verificador revisa que cada cifra del texto aparezca en lo que devolvieron las herramientas.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app import geo, indicators, narrativa
from app.data import analitica, buscar_fichas, catalogo, info

# Alias "latest" de Gemini Flash; si tu curso usa otro modelo, cámbialo con la variable GEMINI_MODEL.
MODELO = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
MAX_VUELTAS = 6

SISTEMA = """Eres el analista de Termómetro BCRP + El Niño. Hablas con emprendedores que NO saben de economía.
Reglas:
1. Solo puedes usar datos que te devuelvan tus herramientas (series oficiales del BCRP/NOAA del catálogo). Si te preguntan algo que las herramientas no cubren, dilo con claridad y no inventes.
2. Nunca des una cifra que no venga de una herramienta. No hagas cálculos propios con cifras: usa los resúmenes que entregan las herramientas.
3. Usa palabras simples y explica cualquier término técnico en una frase. Respuestas cortas (máximo 150 palabras), con un ejemplo práctico para un negocio cuando ayude.
4. Menciona la fuente al final (nombre de la serie y código BCRPData cuando lo tengas).
5. No des recomendaciones de inversión ni asesoría legal. Puedes explicar riesgos y qué mirar.
6. Que dos series se muevan juntas no prueba causalidad: dilo cuando hables de El Niño y precios.
7. Si una serie figura como no verificada, avísalo."""

HERRAMIENTAS = [
    {"name": "listar_series", "description": "Lista las series disponibles (id, nombre, unidad, tema). Úsala si no sabes qué serie corresponde.",
     "input_schema": {"type": "object", "properties": {"tema": {"type": "string", "description": "Opcional: precios, tipo_de_cambio, actividad, tasas, mercado_laboral, pesca"}}}},
    {"name": "resumen_serie", "description": "Resumen en lenguaje simple de los últimos 6 meses y del último año de una serie, con sus cifras.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "datos_serie", "description": "Últimas observaciones de una serie (ya transformada, p. ej. inflación a 12 meses).",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}, "ultimos": {"type": "integer", "description": "Cantidad de observaciones (máximo 36)"}}, "required": ["id"]}},
    {"name": "semaforo", "description": "Semáforo de exposición de un tipo de negocio, con razones y umbrales de alerta.",
     "input_schema": {"type": "object", "properties": {"perfil": {"type": "string", "enum": list(indicators.PERFILES)}}, "required": ["perfil"]}},
    {"name": "exposicion_regional", "description": "Pesca de anchoveta por región (Piura, La Libertad, Áncash, Lima, Ica): volumen, participación y caída en episodios El Niño.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "buscar_fichas", "description": "Busca explicaciones en lenguaje simple (fichas) sobre un concepto o serie.",
     "input_schema": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]}},
]


def ejecutar_herramienta(nombre: str, args: dict, series_dir: Path | None = None) -> dict:
    """Ejecuta una herramienta. Devuelve siempre un dict serializable; los errores se informan, no se lanzan."""
    try:
        if nombre == "listar_series":
            tema = args.get("tema")
            return {"series": [{"id": s["id"], "nombre": s["nombre"], "unidad": s["unidad"], "tema": s["tema"],
                                "verificada": s["verificada"]} for s in catalogo() if not tema or s["tema"] == tema]}
        if nombre == "resumen_serie":
            r = narrativa.resumen(args["id"], series_dir)
            return {"id": r["id"], "nombre": info(r["id"])["nombre"], "codigo_bcrp": info(r["id"])["code"],
                    "verificada": info(r["id"])["verificada"], "frases": r["frases"], "fecha_ultimo": r["fecha_ultimo"],
                    "valor_ultimo": r["valor_ultimo"]}
        if nombre == "datos_serie":
            n = max(1, min(int(args.get("ultimos", 12)), 36))
            d = analitica(args["id"], series_dir).dropna().tail(n)
            return {"id": args["id"], "codigo_bcrp": info(args["id"])["code"],
                    "observaciones": [{"fecha": r.fecha.strftime("%Y-%m"), "valor": round(float(r.valor), 3)} for r in d.itertuples()]}
        if nombre == "semaforo":
            return indicators.evaluar(args["perfil"], series_dir)
        if nombre == "exposicion_regional":
            t = geo.tabla_regional(series_dir)
            cols = ["nombre", "toneladas_12m", "participacion_pct", "caida_promedio_episodios"]
            return {"regiones": t[cols].round(1).to_dict("records") if not t.empty else [],
                    "nota": "Solo las 5 regiones incluidas en el catálogo."}
        if nombre == "buscar_fichas":
            return {"fichas": [{"id": f["id"], "texto": f["texto"]} for f in buscar_fichas(args["consulta"])]}
        return {"error": f"Herramienta desconocida: {nombre}"}
    except KeyError as e:
        return {"error": f"Serie o dato fuera del catálogo: {e}"}
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}


# ---------- verificador de cifras ----------
_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?")


def _a_float(s: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def _decimales(s: str) -> int:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        return len(s.split(".")[1]) if "." in s else 0
    m = re.search(r"[.,](\d+)$", s)
    return len(m.group(1)) if m else 0


def cifras_no_respaldadas(texto: str, resultados: list[str]) -> list[str]:
    """Números del texto que no aparecen (con redondeo razonable) en los resultados de las herramientas."""
    base = [abs(_a_float(m)) for r in resultados for m in _NUM.findall(r.replace("-", ""))]
    malos = []
    for m in _NUM.findall(texto):
        v = abs(_a_float(m))
        if float(v).is_integer() and 0 <= v <= 12:
            continue
        if re.fullmatch(r"(19|20)\d{2}", m):
            continue
        tol = 0.5 * 10 ** (-_decimales(m)) + 1e-9
        if not any(abs(v - b) <= tol for b in base):
            malos.append(m)
    return malos


def _declaraciones():
    from google.genai import types
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(name=h["name"], description=h["description"], parameters_json_schema=h["input_schema"])
        for h in HERRAMIENTAS])]


def _contenido(historial: list[dict], pregunta: str) -> list:
    from google.genai import types
    out = [types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
           for m in historial]
    out.append(types.Content(role="user", parts=[types.Part(text=pregunta)]))
    return out


def responder(cliente, historial: list[dict], pregunta: str, series_dir: Path | None = None,
              modelo: str = MODELO) -> dict:
    """Ciclo de llamadas a herramientas con Gemini. 'historial' son mensajes previos {role, content: str}."""
    from google.genai import types
    contenidos = _contenido(historial, pregunta)
    config = types.GenerateContentConfig(
        system_instruction=SISTEMA, tools=_declaraciones(), max_output_tokens=1500,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    resultados: list[str] = []
    usadas: list[str] = []
    for _ in range(MAX_VUELTAS):
        resp = cliente.models.generate_content(model=modelo, contents=contenidos, config=config)
        llamadas = resp.function_calls or []
        if not llamadas:
            texto = (resp.text or "").strip()
            return {"texto": texto, "herramientas": usadas, "advertencias": cifras_no_respaldadas(texto, resultados)}
        contenidos.append(resp.candidates[0].content)   # se conserva tal cual (incluye las firmas de razonamiento)
        partes = []
        for c in llamadas:
            salida = ejecutar_herramienta(c.name, dict(c.args or {}), series_dir)
            txt = json.dumps(salida, ensure_ascii=False, default=str)
            resultados.append(txt)
            usadas.append(c.name)
            partes.append(types.Part.from_function_response(name=c.name, response={"resultado": json.loads(txt)}))
        contenidos.append(types.Content(role="user", parts=partes))
    return {"texto": "No pude completar la consulta. Intenta con una pregunta más específica.", "herramientas": usadas,
            "advertencias": []}
