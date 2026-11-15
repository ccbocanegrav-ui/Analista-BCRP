"""Termómetro BCRP + El Niño. Ejecutar con:  streamlit run app/streamlit_app.py"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from app import chat, estructurado, geo, negocio, narrativa, nino, periodista, plan, voz  # noqa: E402
from app.data import SERIES_DIR, analitica, catalogo, ficha, info  # noqa: E402
from app.indicators import PERFILES, evaluar  # noqa: E402

load_dotenv()
st.set_page_config(page_title="Termómetro BCRP + El Niño", page_icon="🌡️", layout="wide")

AZUL, NARANJA, ROJO, GRIS = "#1f5fbf", "#d9822b", "#c0392b", "#9aa5b1"
EMOJI = {"rojo": "🔴", "amarillo": "🟡", "verde": "🟢", "gris": "⚪"}
TEMAS = {"tipo_de_cambio": "Dólar", "precios": "Precios", "actividad": "Economía y producción", "tasas": "Tasas de interés",
         "mercado_laboral": "Empleo", "pesca": "Pesca"}


# ---------- utilidades ----------
@st.cache_data(show_spinner=False)
def _analitica(sid: str, firma: float) -> pd.DataFrame:
    return analitica(sid)


def _firma(sid: str) -> float:
    ruta = SERIES_DIR / f"{sid}.csv"
    return ruta.stat().st_mtime if ruta.exists() else 0.0


def serie(sid: str) -> pd.DataFrame:
    return _analitica(sid, _firma(sid))


def hay(sid: str) -> bool:
    return (SERIES_DIR / f"{sid}.csv").exists()


def grafico(sid: str, desde_anio: int, resaltar_6m: bool = True):
    df = serie(sid)
    df = df[df["fecha"] >= pd.Timestamp(f"{desde_anio}-01-01")]
    meta = info(sid)
    fig = go.Figure(go.Scatter(x=df["fecha"], y=df["valor"], mode="lines", line=dict(color=AZUL, width=2), name=meta["nombre"]))
    if resaltar_6m and len(df) > 6:
        fin = df["fecha"].max()
        fig.add_vrect(x0=fin - pd.DateOffset(months=6), x1=fin, fillcolor=NARANJA, opacity=0.12, line_width=0,
                      annotation_text="últimos 6 meses", annotation_position="top left")
    fig.update_layout(title=meta["nombre"], yaxis_title=meta["unidad"], xaxis_title="", height=380, margin=dict(t=50, b=10),
                      showlegend=False)
    st.plotly_chart(fig, width="stretch")


def clave_api():
    try:
        k = st.secrets.get("GEMINI_API_KEY", None)
    except Exception:  # noqa: BLE001
        k = None
    return k or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def boton_audio(texto: str, clave: str):
    """Botón que lee el texto en voz alta (sesión 15: texto a voz)."""
    if st.button("🔊 Escuchar", key=f"audio_{clave}"):
        try:
            st.audio(voz.sintetizar(texto), format="audio/mp3")
        except RuntimeError as e:
            st.warning(str(e))


def aviso_sin_datos():
    st.error("Todavía no hay datos descargados. Ejecuta `python scripts/fetch_bcrp.py` y vuelve a abrir la app.")


# ---------- cabecera ----------
st.title("🌡️ Termómetro BCRP + El Niño")
st.caption("Explicamos la economía peruana con datos oficiales del BCRP, en palabras simples, para quien tiene un negocio.")

with st.sidebar:
    st.header("Cómo usar esta app")
    st.markdown("- **Resumen**: cómo está la economía hoy.\n- **Series**: cada indicador explicado.\n- **El Niño**: qué es y cómo pega a la pesca y los precios.\n"
                "- **Mapa y sensibilidad**: qué regiones dependen más de la pesca.\n- **Mi negocio**: semáforo, simulador y plan.\n- **Periodista** y **Chat**.")
    st.info("Los números los calcula el código con datos del BCRP. Los textos explican, no pronostican. "
            "Lo que ves aquí no es asesoría financiera.")
    archivos = list(SERIES_DIR.glob("*.csv")) if SERIES_DIR.exists() else []
    if archivos:
        st.caption("Datos descargados el " + datetime.fromtimestamp(max(a.stat().st_mtime for a in archivos)).strftime("%d/%m/%Y"))

tabs = st.tabs(["Resumen", "Series", "El Niño", "Mapa y sensibilidad", "Mi negocio", "Periodista", "Chat"])

# ---------- Resumen ----------
with tabs[0]:
    st.subheader("¿Cómo está la economía hoy?")
    clave = [("tc_interbancario_venta", "Dólar (S/)"), ("ipc_lima", "Inflación 12 meses (%)"), ("pbi_mensual_yoy", "Crecimiento (%)"),
             ("tasa_referencia", "Tasa del Banco Central (%)"), ("desempleo_lima", "Desempleo Lima (%)"),
             ("harina_precio", "Harina de pescado (US$/t)")]
    clave = [(s, n) for s, n in clave if hay(s)]
    if not clave:
        aviso_sin_datos()
    cols = st.columns(3)
    for i, (sid, nombre) in enumerate(clave):
        try:
            r = narrativa.resumen(sid)
        except (ValueError, FileNotFoundError):
            continue
        with cols[i % 3]:
            delta = r.get("cambio12")
            dec = narrativa.LENGUAJE[sid]["dec"]
            etiqueta = None if delta is None else (f"{delta:+.1f}% vs hace 1 año" if r["tipo"] == "nivel" else f"{delta:+.1f} puntos vs hace 1 año")
            st.metric(nombre, f"{r['valor_ultimo']:,.{dec}f}", etiqueta, delta_color="off")
            st.caption(narrativa.mes_texto(r["fecha_ultimo"]))
            with st.expander("Qué significa"):
                st.write(" ".join(r["frases"]))
    st.divider()
    st.markdown("**Empieza por aquí:** si tienes un negocio, ve a la pestaña **Mi negocio** para ver tu semáforo y simular qué pasaría con tu margen.")

# ---------- Series ----------
with tabs[1]:
    series = [s for s in catalogo() if hay(s["id"])]
    if not series:
        aviso_sin_datos()
    else:
        c1, c2, c3 = st.columns([1, 2, 1])
        temas = sorted({s["tema"] for s in series})
        tema = c1.selectbox("Tema", temas, format_func=lambda t: TEMAS.get(t, t))
        elegida = c2.selectbox("Indicador", [s for s in series if s["tema"] == tema], format_func=lambda s: s["nombre"])
        desde = c3.slider("Desde el año", 2012, 2026, 2020)
        sid = elegida["id"]
        grafico(sid, desde)
        izq, der = st.columns(2)
        with izq:
            st.markdown("#### Qué pasó en los últimos 6 meses y el último año")
            _resumen = narrativa.texto(sid)
            st.write(_resumen)
            boton_audio(_resumen, f"serie_{sid}")
        with der:
            st.markdown("#### En palabras simples")
            st.markdown((ficha(sid) or "_Ficha pendiente._").replace("> BORRADOR: revisa y ajusta con tu criterio antes de presentar.", ""))
        st.caption(f"Fuente: BCRPData, serie {elegida['code']}.")
        if not elegida.get("verificada"):
            st.warning("Esta serie aún no está verificada contra su página en BCRPData.")

# ---------- El Niño ----------
with tabs[2]:
    st.subheader("El Niño costero y tu bolsillo")
    st.write(nino.QUE_ES)
    st.markdown("#### Por dónde llega el golpe")
    cols = st.columns(len(nino.CANALES))
    for c, (titulo, texto) in zip(cols, nino.CANALES):
        c.markdown(f"**{titulo}**")
        c.caption(texto)

    st.markdown("#### Qué dicen los datos: pesca de anchoveta de enero a agosto, año por año")
    if hay(geo.TOTAL):
        anual = geo.serie_anual(geo.TOTAL)
        colores = [ROJO if a in geo.EPISODIOS else GRIS for a in anual["anio"]]
        fig = go.Figure(go.Bar(x=anual["anio"], y=anual["valor"] / 1000, marker_color=colores))
        fig.update_layout(yaxis_title="miles de toneladas", height=340, margin=dict(t=20, b=10), xaxis=dict(dtick=1))
        st.plotly_chart(fig, width="stretch")
        st.caption("En rojo, los años con El Niño costero declarado. Se compara el mismo período (enero–agosto) para que los años sean comparables.")
        filas = []
        for a, nombre in geo.EPISODIOS.items():
            c = geo.caida_en_episodio(geo.TOTAL, a)
            if c is not None:
                filas.append({"Episodio": nombre, "Pesca de anchoveta (ene–ago) vs año anterior": f"{c:+.0f}%"})
        if filas:
            st.table(pd.DataFrame(filas))
        if hay("harina_precio"):
            st.markdown("#### El precio de la harina de pescado")
            grafico("harina_precio", 2012, resaltar_6m=False)
    else:
        aviso_sin_datos()

    st.markdown("#### La temperatura del mar (NOAA)")
    anom = nino.anomalia_mensual()
    if anom is None:
        st.info("Para ver la temperatura del mar, ejecuta `python scripts/fetch_noaa.py`. Mientras tanto, esta sección queda vacía.")
    else:
        fig = go.Figure(go.Scatter(x=anom["fecha"], y=anom["valor"], mode="lines", line=dict(color=ROJO), name="Anomalía del mar (°C)"))
        fig.add_hline(y=0, line_dash="dot", line_color=GRIS)
        fig.update_layout(title="Cuánto más caliente que lo normal está el mar frente a Perú (Niño 1+2)", yaxis_title="°C", height=320,
                          margin=dict(t=50, b=10))
        st.plotly_chart(fig, width="stretch")
        if hay(geo.TOTAL):
            corr = nino.correlacion_con_pesca(anom, geo.cargar(geo.TOTAL))
            if corr:
                st.caption(f"Correlación histórica entre la anomalía del mar y la variación de la pesca: {corr['r']:.2f} (con {corr['n']} meses). "
                           "Una correlación negativa significa que, cuando el mar se calienta, la pesca tiende a caer. No prueba causalidad.")
    with st.expander("Glosario"):
        for k, v in nino.GLOSARIO.items():
            st.markdown(f"**{k}.** {v}")

# ---------- Mapa y sensibilidad ----------
with tabs[3]:
    st.subheader("¿Qué regiones dependen más de la pesca de anchoveta?")
    tabla = geo.tabla_regional() if hay(geo.TOTAL) else pd.DataFrame()
    if tabla.empty:
        aviso_sin_datos()
    else:
        st.write("El mapa muestra cuánta anchoveta se desembarcó en el último año en cada región (tamaño del círculo) y cuánto cayó, en promedio, "
                 "cuando hubo El Niño (color). Cuanto más rojo, más golpeó El Niño a esa región en el pasado.")
        import folium
        from streamlit_folium import st_folium
        m = folium.Map(location=[-9.0, -78.5], zoom_start=6, tiles="OpenStreetMap")
        maxv = tabla["toneladas_12m"].max() or 1
        for r in tabla.itertuples():
            caida = abs(r.caida_promedio_episodios)
            color = "#c0392b" if caida >= 50 else "#e67e22" if caida >= 25 else "#2e86c1"
            folium.CircleMarker(
                location=[r.lat, r.lon], radius=8 + 30 * r.toneladas_12m / maxv, color=color, fill=True, fill_opacity=0.6,
                tooltip=f"{r.nombre} ({r.puerto})",
                popup=folium.Popup(f"<b>{r.nombre}</b><br>Último año: {r.toneladas_12m:,.0f} t<br>"
                                   f"Participación: {r.participacion_pct:.0f}%<br>Caída promedio en El Niño: {r.caida_promedio_episodios:.0f}%",
                                   max_width=260)).add_to(m)
        st_folium(m, height=460, use_container_width=True, returned_objects=[])
        cob = tabla.attrs.get("cobertura_pct")
        st.caption("Ubicación referencial del puerto principal de cada región. "
                   + (f"Estas 5 regiones suman {cob:.0f}% del desembarque nacional del último año. " if cob else "")
                   + "Colores: azul = caída menor a 25%, naranja = 25–50%, rojo = 50% o más.")
        mostrar = tabla[["nombre", "puerto", "toneladas_12m", "participacion_pct", "caida_promedio_episodios", "toneladas_en_riesgo"]].rename(columns={
            "nombre": "Región", "puerto": "Puerto", "toneladas_12m": "Toneladas último año", "participacion_pct": "Participación (%)",
            "caida_promedio_episodios": "Caída promedio en El Niño (%)", "toneladas_en_riesgo": "Toneladas en riesgo"})
        st.dataframe(mostrar.round(1), hide_index=True, width="stretch")

        st.markdown("### Análisis de sensibilidad: ¿y si la pesca cae?")
        st.write("Un análisis de sensibilidad responde preguntas del tipo **«¿y si…?»**: cambia un dato y mira cuánto se mueve el resultado. "
                 "No predice lo que pasará; muestra qué tan expuesta está cada región.")
        caida = st.slider("Si la pesca de anchoveta cae…", 0, 80, 30, step=5, format="%d%%")
        esc = geo.escenario(tabla, caida)
        fig = go.Figure(go.Bar(x=esc["nombre"], y=esc["toneladas_perdidas"] / 1000, marker_color=NARANJA))
        fig.update_layout(yaxis_title="miles de toneladas que se dejarían de pescar", height=320, margin=dict(t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        top = esc.sort_values("toneladas_perdidas", ascending=False).iloc[0]
        st.write(f"Con una caída de {caida}%, la región que más volumen perdería es **{top['nombre']}** "
                 f"(unas {top['toneladas_perdidas']:,.0f} toneladas), por ser la que más pesca concentra.")

        sens = geo.sensibilidad_precio_harina()
        if sens:
            st.markdown("### ¿Cuánto se mueve el precio de la harina cuando cambia la pesca?")
            d = sens["datos"]
            fig = go.Figure(go.Scatter(x=d["x"], y=d["y"], mode="markers", marker=dict(color=AZUL, opacity=0.6), name="meses"))
            xs = [d["x"].min(), d["x"].max()]
            fig.add_trace(go.Scatter(x=xs, y=[sens["intercepto"] + sens["pendiente"] * x for x in xs], mode="lines",
                                     line=dict(color=ROJO), name="tendencia"))
            fig.update_layout(xaxis_title="Cambio de la pesca vs año anterior (%)", yaxis_title="Cambio del precio de la harina (%)",
                              height=340, margin=dict(t=20, b=10))
            st.plotly_chart(fig, width="stretch")
            debil = sens["r2"] < 0.3
            st.write(f"En la historia, cada 10% menos de pesca vino acompañado de un cambio de {-10 * sens['pendiente']:+.1f}% en el precio de la harina "
                     f"(relación estimada con {sens['n']} meses; R² = {sens['r2']:.2f}). "
                     + ("**La relación es débil**: el precio depende de más cosas que la pesca peruana, así que no la uses para predecir." if debil
                        else "La relación es visible, pero describe el pasado: no garantiza lo que pasará."))

# ---------- Mi negocio ----------
with tabs[4]:
    st.subheader("Mi negocio frente a El Niño y a los precios")
    perfil = st.selectbox("¿Cuál es tu negocio?", list(PERFILES))
    res = evaluar(perfil)
    st.markdown(f"### Tu exposición general: {EMOJI[res['general']]} {res['general'].upper()}")
    st.caption("Rojo si 2 o más indicadores están en alerta; amarillo si hay 1 en rojo o 2 o más en amarillo; verde en los demás casos.")
    for ind in res["indicadores"]:
        st.markdown(f"{EMOJI[ind['color']]} **{ind['nombre']}**: {ind['razon']}")
    st.caption(res["advertencia"])

    pl = plan.construir(res)
    st.markdown("### Plan de exposición")
    c1, c2, c3 = st.columns(3)
    for col, h in zip((c1, c2, c3), ("Esta semana", "Próximos 3 meses", "Si empeora")):
        col.markdown(f"**{h}**")
        if not pl["acciones"][h]:
            col.caption("Sin acciones sugeridas con el semáforo actual.")
        for a in pl["acciones"][h]:
            col.markdown(f"- {EMOJI[a['color']]} {a['texto']}")
    st.caption(pl["aviso"])
    if pl["vigilar"]:
        st.markdown("#### Señales a vigilar (cuándo cambia tu semáforo)")
        filas = []
        for v in pl["vigilar"]:
            flecha = "≥" if v["sentido"] == "alza" else "≤"
            filas.append({"Indicador": v["indicador"], "Hoy": f"{v['actual']:.1f}{v['unidad']}",
                          "Pasa a amarillo": f"{flecha} {v['umbral_amarillo']:.1f}{v['unidad']}",
                          "Pasa a rojo": f"{flecha} {v['umbral_rojo']:.1f}{v['unidad']}", "Qué mirar": v["senal"]})
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")

    st.markdown("### Simulador: ¿y si el dólar o mis insumos se mueven?")
    st.write("Cuéntanos cómo está armado tu negocio y mira qué pasa con tu margen. Es un ejercicio de **sensibilidad**, no una predicción.")
    a, b, c = st.columns(3)
    margen = a.number_input("Margen actual (% de las ventas que te queda)", 0.0, 90.0, 15.0, 1.0)
    ing_usd = a.slider("Parte de tus ventas en dólares (%)", 0, 100, 0)
    cos_usd = b.slider("Parte de tus costos en dólares (%)", 0, 100, 30)
    cos_ins = b.slider("Parte de tus costos en insumos locales (alimentos, etc.) (%)", 0, 100 - cos_usd, min(40, 100 - cos_usd))
    t = c.slider("Si el dólar cambia (%)", -15, 30, 10)
    p = c.slider("Si tus insumos locales suben (%)", 0, 30, 5)
    r = negocio.margen_resultante(margen, ing_usd, cos_usd, t, cos_ins, p)
    m1, m2 = st.columns(2)
    m1.metric("Tu margen pasaría de", f"{margen:.1f}%", f"{r['cambio_pp']:+.1f} puntos", delta_color="normal")
    m2.metric("A", f"{r['margen_nuevo']:.1f}%")
    g = negocio.grilla_tc(margen, ing_usd, cos_usd, cos_ins, p)
    fig = go.Figure(go.Scatter(x=[x["var_tc_pct"] for x in g], y=[x["margen_nuevo"] for x in g], mode="lines+markers", line=dict(color=AZUL)))
    fig.add_hline(y=0, line_dash="dot", line_color=ROJO)
    fig.update_layout(xaxis_title="Cambio del dólar (%)", yaxis_title="Margen resultante (%)", height=300, margin=dict(t=20, b=10))
    st.plotly_chart(fig, width="stretch")
    eq = negocio.tc_que_anula_margen(margen, ing_usd, cos_usd, cos_ins, p)
    if eq is not None and eq > 0:
        st.write(f"Con estos datos, tu margen llegaría a cero si el dólar subiera cerca de **{eq:.0f}%**.")
    elif eq is not None and eq < 0:
        st.write(f"Con estos datos, tu margen llegaría a cero si el dólar bajara cerca de **{abs(eq):.0f}%**.")
    else:
        st.write("Con estos datos, el dólar por sí solo no lleva tu margen a cero.")

    st.markdown("### Mi zona")
    tabla2 = geo.tabla_regional() if hay(geo.TOTAL) else pd.DataFrame()
    if not tabla2.empty:
        zona = st.selectbox("¿En qué región está tu negocio?", ["Otra región"] + list(tabla2["nombre"]))
        fila = tabla2[tabla2["nombre"] == zona]
        if fila.empty:
            st.caption("Esa región no está entre las 5 con series de pesca en la app. Aun así, El Niño puede afectarte por precios y transporte.")
        else:
            f = fila.iloc[0]
            st.write(f"**{zona}** concentra {f['participacion_pct']:.0f}% de la anchoveta de estas 5 regiones. En años de El Niño, "
                     f"su pesca cayó en promedio {abs(f['caida_promedio_episodios']):.0f}% frente al año anterior. "
                     "Si tu negocio depende de la pesca o de quienes viven de ella, tu zona está más expuesta.")

# ---------- Periodista ----------
with tabs[5]:
    st.subheader("Modo periodista")
    st.write("Una nota lista con cifras oficiales. Puedes editarla y el verificador te avisa si alguna cifra no sale de los datos.")
    hs = periodista.hechos()
    base = periodista.nota_plantilla(hs)
    texto = st.text_area("Nota (puedes editarla)", base, height=200)
    if st.button("Verificar cifras"):
        malos = periodista.verificar_numeros(texto, hs)
        if malos:
            st.error(f"Cifras que no provienen de los datos: {', '.join(malos)}")
        else:
            st.success("Todas las cifras coinciden con los datos del BCRP.")
    boton_audio(texto, "periodista")
    st.markdown("#### Redactar con IA (salida estructurada)")
    st.caption("El modelo recibe solo los hechos calculados y debe devolver un formato fijo (titular, bajada, puntos con su cifra y serie). "
               "Si una cifra no sale de los datos, se marca.")
    if st.button("Redactar con IA") and hs:
        if not clave_api():
            st.info("Necesitas la API key de Gemini para usar esta función.")
        else:
            try:
                from google import genai
                nota, malos = estructurado.generar(genai.Client(api_key=clave_api()), hs)
                st.markdown(f"**{nota.titular}**")
                st.write(nota.bajada)
                for pto in nota.puntos:
                    st.markdown(f"- {pto.texto} _(serie {pto.serie})_")
                st.caption(f"Fuente: {nota.fuente}")
                if malos:
                    st.warning("Cifras que no salen de los datos: " + ", ".join(malos))
                else:
                    st.success("Estructura válida y todas las cifras verificadas.")
                with st.expander("Ver el JSON estructurado"):
                    st.json(nota.model_dump())
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo generar la nota: {e}")

# ---------- Chat ----------
with tabs[6]:
    st.subheader("Pregúntale al analista")
    st.caption("Responde solo con las series de la app. Si no tiene el dato, te lo dice.")
    _clave = clave_api()
    if not _clave:
        st.info("El chat necesita una API key de Gemini (variable `GEMINI_API_KEY` en `.env` o en los secretos de Streamlit).")
    else:
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
        ejemplos = ["¿Cómo está el dólar y qué significa para mi negocio?", "¿Qué es El Niño y cómo afecta los precios?",
                    "¿Qué región depende más de la anchoveta?"]
        if not st.session_state.chat:
            st.caption("Prueba con: " + " · ".join(f"«{e}»" for e in ejemplos))
        pregunta = st.chat_input("Escribe tu pregunta")
        if pregunta:
            with st.chat_message("user"):
                st.write(pregunta)
            with st.chat_message("assistant"):
                with st.spinner("Consultando los datos…"):
                    try:
                        from google import genai
                        out = chat.responder(genai.Client(api_key=_clave), st.session_state.chat[-8:], pregunta)
                        st.write(out["texto"])
                        if out["advertencias"]:
                            st.warning("Cifras que no pude verificar en los datos consultados: " + ", ".join(out["advertencias"]))
                        if out["herramientas"]:
                            st.caption("Consultó: " + ", ".join(sorted(set(out["herramientas"]))))
                        st.session_state.chat += [{"role": "user", "content": pregunta}, {"role": "assistant", "content": out["texto"]}]
                    except Exception as e:  # noqa: BLE001
                        st.error(f"No se pudo responder: {e}")

    with st.expander("Cómo medimos la calidad del chat (evaluación)"):
        ruta_eval = Path(__file__).resolve().parents[1] / "docs" / "evaluacion.md"
        if ruta_eval.exists():
            st.markdown(ruta_eval.read_text(encoding="utf-8"))
        else:
            st.caption("Ejecuta `python scripts/evaluar.py` para generar el informe.")
