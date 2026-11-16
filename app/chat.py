"""Chat analista (Gemini): el modelo solo puede consultar las series del catálogo mediante herramientas.

Los números los entregan las herramientas (código); el modelo los explica en lenguaje simple.
Después de responder, un verificador revisa que cada cifra del texto aparezca en lo que devolvieron las herramientas.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from app import docs, geo, indicators, narrativa, negocio, plan
import pandas as pd

from app.data import analitica, buscar_fichas, catalogo, externa, info

# Alias "latest" de Gemini Flash; si tu curso usa otro modelo, cámbialo con la variable GEMINI_MODEL.
MODELO = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")   # solo se usa si no se puede consultar la lista de modelos
MAX_VUELTAS = 6
_MODELO_CACHE: dict[int, list[str]] = {}

SISTEMA = """Eres el analista de Termómetro BCRP + El Niño. Hablas con emprendedores que NO saben de economía.
Reglas:
1. Solo puedes usar datos que te devuelvan tus herramientas (series oficiales del BCRP/NOAA del catálogo). Si te preguntan algo que las herramientas no cubren, dilo con claridad y no inventes.
2. Nunca des una cifra que no venga de una herramienta. No hagas cálculos propios con cifras: usa los resúmenes que entregan las herramientas.
3. Usa palabras simples y explica cualquier término técnico en una frase. Respuestas cortas (máximo 150 palabras), con un ejemplo práctico para un negocio cuando ayude.
4. Menciona la fuente al final: para series, el nombre y el código BCRPData; para documentos, el nombre y la página que devolvió la herramienta. Para causas, proyecciones o contexto usa buscar_documentos y di claramente que es lo que dice ese documento.
5. No des recomendaciones de inversión ni asesoría legal. Puedes explicar riesgos y qué mirar.
6. Que dos series se muevan juntas no prueba causalidad: dilo cuando hables de El Niño y precios.
7. Si una serie figura como no verificada, avísalo.
8. Formato: primero la respuesta directa en 1 o 2 frases; luego "Qué significa para ti" con un ejemplo práctico; al final "Fuente:". Si la pregunta es ambigua, haz UNA pregunta corta antes de responder.
9. Si el usuario te cuenta de su negocio (abajo, en CONTEXTO DEL USUARIO), personaliza la respuesta con esos datos y usa el simulador cuando pregunte por su margen. No inventes datos de su negocio.
10. Cierra siempre con una línea "Podrías preguntar:" seguida de 2 preguntas de seguimiento cortas, cada una en su línea y que empiece con "- "."""

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
    {"name": "simular_margen", "description": "Simula cómo cambia el margen de un negocio si el dólar o los insumos locales se mueven. Todos los parámetros son porcentajes.",
     "input_schema": {"type": "object", "properties": {
         "margen_pct": {"type": "number"}, "ingreso_usd_pct": {"type": "number"}, "costo_usd_pct": {"type": "number"},
         "var_tc_pct": {"type": "number"}, "costo_insumos_pct": {"type": "number"}, "var_insumos_pct": {"type": "number"}},
         "required": ["margen_pct", "ingreso_usd_pct", "costo_usd_pct", "var_tc_pct"]}},
    {"name": "anomalia_nino", "description": "Temperatura del mar frente a Perú (anomalía Niño 1+2 de NOAA, semanal): últimas semanas, máximo del último año y máximo histórico. Úsala para saber cómo está El Niño ahora.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "episodios_el_nino", "description": "Cuánto cayó la pesca de anchoveta (enero a agosto) frente al año anterior en 2017, 2023 y 2026, a nivel nacional.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "plan_exposicion", "description": "Acciones sugeridas por horizonte y señales a vigilar para un tipo de negocio, según su semáforo.",
     "input_schema": {"type": "object", "properties": {"perfil": {"type": "string", "enum": list(indicators.PERFILES)}}, "required": ["perfil"]}},
    {"name": "buscar_documentos", "description": "Busca en los documentos oficiales indexados (reportes del BCRP, comunicados del ENFEN, etc.). Úsala para explicar causas, proyecciones y contexto. Devuelve fragmentos con documento y página.",
     "input_schema": {"type": "object", "properties": {"consulta": {"type": "string"}}, "required": ["consulta"]}},
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
        if nombre == "simular_margen":
            a = {k: float(v) for k, v in args.items()}
            r = negocio.margen_resultante(a["margen_pct"], a["ingreso_usd_pct"], a["costo_usd_pct"], a["var_tc_pct"],
                                          a.get("costo_insumos_pct", 0.0), a.get("var_insumos_pct", 0.0))
            eq = negocio.tc_que_anula_margen(a["margen_pct"], a["ingreso_usd_pct"], a["costo_usd_pct"],
                                             a.get("costo_insumos_pct", 0.0), a.get("var_insumos_pct", 0.0))
            return {"margen_nuevo_pct": round(r["margen_nuevo"], 2), "cambio_en_puntos": round(r["cambio_pp"], 2),
                    "variacion_del_dolar_que_anula_el_margen_pct": None if eq is None else round(eq, 1),
                    "nota": "Ejercicio de sensibilidad, no una predicción."}
        if nombre == "anomalia_nino":
            d = externa("nino12_anomalia", series_dir)
            if d is None or d.empty:
                return {"error": "No se descargó la serie de NOAA. Ejecuta scripts/fetch_noaa.py"}
            d = d.dropna().sort_values("fecha")
            ultimo_anio = d[d.fecha > d.fecha.max() - pd.Timedelta(days=365)]
            pico = d.loc[d.valor.idxmax()]
            return {"unidad": "°C sobre lo normal", "fuente": "NOAA CPC, región Niño 1+2", "verificada": False,
                    "ultimas_semanas": [{"semana": r.fecha.strftime("%Y-%m-%d"), "anomalia": round(float(r.valor), 1)}
                                        for r in d.tail(4).itertuples()],
                    "maximo_ultimo_anio": round(float(ultimo_anio.valor.max()), 1),
                    "maximo_historico": {"semana": pico.fecha.strftime("%Y-%m-%d"), "anomalia": round(float(pico.valor), 1)},
                    "nota": "Anomalía = cuánto más caliente está el mar que lo normal. Serie marcada como no verificada en el catálogo."}
        if nombre == "episodios_el_nino":
            filas = []
            for a, n in geo.EPISODIOS.items():
                c = geo.caida_en_episodio(geo.TOTAL, a, series_dir)
                filas.append({"episodio": n, "variacion_pesca_ene_ago_pct": None if c is None else round(c, 1)})
            return {"episodios": filas, "nota": "Años con El Niño costero según ENFEN (verificar). Compara enero–agosto con el año anterior."}
        if nombre == "plan_exposicion":
            ev = indicators.evaluar(args["perfil"], series_dir)
            pl = plan.construir(ev)
            return {"semaforo_general": ev["general"], "acciones": pl["acciones"], "senales_a_vigilar": pl["vigilar"], "aviso": pl["aviso"]}
        if nombre == "buscar_documentos":
            r = docs.buscar(args["consulta"])
            return {"fragmentos": r} if r else {"fragmentos": [], "nota": "No hay documentos indexados o no hay coincidencias."}
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
    base = [abs(_a_float(m)) for r in resultados for m in _NUM.findall(r.replace("-", " "))]
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


def _version(nombre: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)-flash", nombre)
    return float(m.group(1)) if m else 0.0


def elegir_modelo(cliente) -> str:
    """Si GEMINI_MODEL está definido, lo usa. Si no, pregunta a la API qué modelos Flash estables tiene tu clave y elige el más nuevo."""
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    return modelos_candidatos(cliente)[0]


def modelos_candidatos(cliente) -> list[str]:
    """Modelos Flash estables en orden de preferencia (GEMINI_MODEL primero, si está). Se usan de respaldo uno tras otro,
    porque en el plan gratuito cada modelo tiene su propia cuota diaria."""
    preferido = os.environ.get("GEMINI_MODEL")
    if id(cliente) not in _MODELO_CACHE:
        _MODELO_CACHE[id(cliente)] = _listar_flash(cliente)
    lista = _MODELO_CACHE[id(cliente)]
    return ([preferido] if preferido else []) + [m for m in lista if m != preferido] or [MODELO]


def _listar_flash(cliente) -> list[str]:
    candidatos = []
    try:
        for m in cliente.models.list():
            nombre = (getattr(m, "name", "") or "").replace("models/", "")
            acciones = getattr(m, "supported_actions", None) or []
            if "generateContent" not in acciones or "flash" not in nombre or "latest" in nombre:
                continue
            if any(x in nombre for x in ("lite", "image", "tts", "live", "audio", "embedding", "preview", "exp", "thinking", "robotics")):
                continue
            candidatos.append(nombre)
    except Exception:  # noqa: BLE001
        pass
    return sorted(candidatos, key=lambda n: (_version(n), -len(n)), reverse=True) or [MODELO]


def _es_recuperable(e: Exception) -> bool:
    """Errores en que conviene probar con otro modelo: cuota agotada (429), saturación (5xx) o tiempo de espera."""
    codigo = getattr(e, "code", None)
    if codigo in (404, 429, 500, 503, 504):   # 404: modelo retirado para tu cuenta
        return True
    return "timeout" in type(e).__name__.lower()


def con_respaldo(cliente, funcion, modelo: str | None = None):
    """Ejecuta funcion(modelo) con el modelo indicado o, si no se indica, con cada candidato hasta que uno funcione."""
    modelos = [modelo] if modelo else modelos_candidatos(cliente)
    fallos: dict[str, Exception] = {}
    for vuelta in range(2):   # 2.ª vuelta: solo los saturados (5xx), que suelen recuperarse en segundos
        pendientes = modelos if vuelta == 0 else [m for m, e in fallos.items() if getattr(e, "code", None) in (500, 503)]
        if vuelta and pendientes:
            time.sleep(8)
        for m in pendientes:
            try:
                return funcion(m)
            except Exception as e:  # noqa: BLE001
                if not _es_recuperable(e):
                    raise
                fallos[m] = e
    raise SinModeloDisponible(fallos)


class SinModeloDisponible(RuntimeError):
    """Ningún modelo respondió. El mensaje explica en simple qué pasó con cada uno."""

    def __init__(self, fallos: dict[str, Exception]):
        self.fallos = fallos
        grupos = {"sin cuota por hoy": [], "saturados por Google": [], "no disponibles": []}
        for m, e in fallos.items():
            codigo = getattr(e, "code", None)
            grupo = "sin cuota por hoy" if codigo == 429 else "no disponibles" if codigo == 404 else "saturados por Google"
            grupos[grupo].append(m)
        detalle = "; ".join(f"{k}: {', '.join(v)}" for k, v in grupos.items() if v)
        super().__init__(f"Ningún modelo de Gemini está disponible ahora ({detalle}). "
                         "Si es cuota, se reinicia cada día; si es saturación, intenta de nuevo en unos minutos.")


CACHE_CHAT = Path(__file__).resolve().parents[1] / "data" / "cache_chat.json"
CACHE_HORAS = 24


def _clave_cache(historial: list[dict], pregunta: str, contexto: str) -> str:
    import hashlib
    base = json.dumps([[m["role"], m["content"]] for m in historial] + [pregunta.strip().lower(), contexto], ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _leer_cache() -> dict:
    try:
        return json.loads(CACHE_CHAT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def separar_seguimientos(texto: str) -> tuple[str, list[str]]:
    """Separa el cuerpo de la respuesta de las preguntas sugeridas ('Podrías preguntar:')."""
    m = re.search(r"\n?\s*\**Podrías preguntar:?\**\s*\n", texto, flags=re.I)
    if not m:
        return texto.strip(), []
    cuerpo, resto = texto[:m.start()].strip(), texto[m.end():]
    preguntas = [re.sub(r"^[-•*\d.\s]+", "", l).strip() for l in resto.splitlines() if l.strip()]
    return cuerpo, [q for q in preguntas if q.endswith("?")][:3]


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


def _generar(cliente, modelo, contenidos, config, intentos: int = 2, espera: float = 5.0):
    """Llama a Gemini; si el servidor está saturado (503) reintenta una vez antes de pasar a otro modelo."""
    for i in range(intentos):
        try:
            return cliente.models.generate_content(model=modelo, contents=contenidos, config=config)
        except Exception as e:  # noqa: BLE001
            if getattr(e, "code", None) != 503 or i == intentos - 1:
                raise
            time.sleep(espera)


def responder(cliente, historial: list[dict], pregunta: str, series_dir: Path | None = None,
              modelo: str | None = None, contexto: str = "", usar_cache: bool = False, rapido: bool = False) -> dict:
    """Ciclo de llamadas a herramientas con Gemini. 'historial' son mensajes previos {role, content: str}.
    Si un modelo se queda sin cuota o está saturado, la pregunta se repite con el siguiente modelo Flash.
    Con usar_cache=True, una pregunta idéntica hecha en las últimas 24 h se responde sin llamar a Gemini."""
    if usar_cache:
        clave = _clave_cache(historial, pregunta, contexto)
        guardado = _leer_cache().get(clave)
        if guardado and time.time() - guardado.get("t", 0) < CACHE_HORAS * 3600:
            return guardado["out"]
    from app import rapido as modo_rapido
    if rapido and modo_rapido.sirve(pregunta, contexto):   # 1 llamada por pregunta (ver app/rapido.py)
        out = modo_rapido.responder(cliente, historial, pregunta, series_dir, modelo, contexto)
    else:
        out = con_respaldo(cliente, lambda m: {**_responder_con(cliente, historial, pregunta, series_dir, m, contexto), "modelo": m}, modelo)
    if usar_cache and out.get("herramientas"):
        cache = _leer_cache()
        cache[clave] = {"t": time.time(), "out": out}
        try:
            CACHE_CHAT.write_text(json.dumps(cache, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError:
            pass
    return out


def _responder_con(cliente, historial: list[dict], pregunta: str, series_dir: Path | None, modelo: str, contexto: str) -> dict:
    from google.genai import types
    contenidos = _contenido(historial, pregunta)
    config = types.GenerateContentConfig(
        system_instruction=SISTEMA + (f"\n\nCONTEXTO DEL USUARIO (datos que él declaró):\n{contexto}" if contexto else ""), tools=_declaraciones(), max_output_tokens=1500,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=45_000))   # 45 s por llamada: si Gemini se cuelga, da error en vez de esperar para siempre
    resultados: list[str] = []
    usadas: list[str] = []
    trazas: list[dict] = []
    for _ in range(MAX_VUELTAS):
        resp = _generar(cliente, modelo, contenidos, config)
        llamadas = resp.function_calls or []
        if not llamadas:
            texto = (resp.text or "").strip()
            cuerpo, seguimientos = separar_seguimientos(texto)
            return {"texto": cuerpo, "seguimientos": seguimientos, "herramientas": usadas, "trazas": trazas,
                    "advertencias": cifras_no_respaldadas(cuerpo, resultados + [contexto, pregunta])}
        contenidos.append(resp.candidates[0].content)   # se conserva tal cual (incluye las firmas de razonamiento)
        partes = []
        for c in llamadas:
            salida = ejecutar_herramienta(c.name, dict(c.args or {}), series_dir)
            txt = json.dumps(salida, ensure_ascii=False, default=str)
            resultados.append(txt)
            usadas.append(c.name)
            trazas.append({"herramienta": c.name, "args": dict(c.args or {}), "resultado": json.loads(txt)})
            partes.append(types.Part.from_function_response(name=c.name, response={"resultado": json.loads(txt)}))
        contenidos.append(types.Content(role="user", parts=partes))
    return {"texto": "No pude completar la consulta. Intenta con una pregunta más específica.", "seguimientos": [],
            "herramientas": usadas, "trazas": trazas, "advertencias": []}
