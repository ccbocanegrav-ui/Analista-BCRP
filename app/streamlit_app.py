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

from app import chat, docs, geo, negocio, narrativa, nino, noticia, plan, voz  # noqa: E402
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
st.caption("Tu analista económico de bolsillo: te explica en palabras simples cómo el dólar, los precios y El Niño afectan "
           "a tu negocio, con datos oficiales del BCRP y de NOAA.")
c1, c2, c3, c4 = st.columns(4)
c1.markdown("🍰 **Alimentos**  \nrepostería, restaurantes, bodegas")
c2.markdown("🐟 **Pesca y mar**  \ncevicherías, pescadores, plantas")
c3.markdown("📦 **Comercio**  \nlo que compras en dólares")
c4.markdown("🍇 **Agro**  \nproductores y agroexportadores")

with st.sidebar:
    st.header("Cómo usar esta app")
    st.markdown("- **Resumen**: cómo está la economía hoy.\n- **Series**: cada indicador explicado.\n- **El Niño**: qué es y cómo pega a la pesca y los precios.\n"
                "- **Mapa y sensibilidad**: qué regiones dependen más de la pesca.\n- **Mi negocio**: semáforo, simulador y plan.\n- **Explícame una noticia**: pega algo que no entendiste.\n- **Chat**: pregúntale al analista.")
    st.info("Los números los calcula el código con datos del BCRP. Los textos explican, no pronostican. "
            "Lo que ves aquí no es asesoría financiera.")
    archivos = list(SERIES_DIR.glob("*.csv")) if SERIES_DIR.exists() else []
    if archivos:
        st.caption("Datos descargados el " + datetime.fromtimestamp(max(a.stat().st_mtime for a in archivos)).strftime("%d/%m/%Y"))

tabs = st.tabs(["Resumen", "Series", "El Niño", "Mapa y sensibilidad", "Mi negocio", "Explícame una noticia", "Chat"])

# ---------- Resumen ----------
with tabs[0]:
    st.subheader("¿Cómo está la economía hoy?")
    clave = [("tc_interbancario_venta", "Dólar (S/)"), ("ipc_lima", "Inflación 12 meses (%)"),
             ("ipc_alimentos_var", "Precios de alimentos (variación %)"), ("pbi_mensual_yoy", "Crecimiento (%)"),
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

# ---------- Explícame una noticia ----------
with tabs[5]:
    st.subheader("¿Leíste algo que no entendiste? Pégalo aquí")
    st.write("Pega una noticia, un comunicado o un párrafo de un informe (o sube un archivo). Te lo explico en palabras simples, te aclaro los términos "
             "técnicos y te muestro qué dicen hoy los datos oficiales del BCRP sobre ese tema.")
    texto_noticia = st.text_area("Texto", height=220, placeholder="Pega aquí la noticia o el párrafo…")
    archivo = st.file_uploader("…o sube un archivo", type=["pdf", "txt", "md"])
    if st.button("Explicar", type="primary"):
        if archivo is not None:
            texto_noticia = noticia.leer_archivo(archivo.name, archivo.getvalue())
        if not clave_api():
            st.info("Necesitas la API key de Gemini para usar esta función.")
        else:
            try:
                from google import genai
                with st.spinner("Leyendo y explicando…"):
                    an, malos, recortado = noticia.analizar(genai.Client(api_key=clave_api()), texto_noticia)
                    st.session_state.noticia = dict(an=an, malos=malos, recortado=recortado,
                                                    datos=noticia.datos_relacionados(an.temas))
            except ValueError as e:
                st.warning(str(e))
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo explicar el texto: {e}")
    res_n = st.session_state.get("noticia")
    if res_n:
        an = res_n["an"]
        if res_n["recortado"]:
            st.caption(f"El texto era largo: se analizaron solo los primeros {noticia.LIMITE_CARACTERES:,} caracteres.")
        st.markdown("### En pocas palabras")
        st.write(an.resumen_simple)
        boton_audio(an.resumen_simple, "noticia")
        if an.terminos:
            st.markdown("### Palabras que quizá no conoces")
            for t in an.terminos:
                st.markdown(f"**{t.termino}.** {t.explicacion}")
            for f in noticia.fichas_para([t.termino for t in an.terminos]):
                with st.expander(f"Ficha de la app relacionada con «{f['termino']}»"):
                    st.markdown(f["texto"].replace("> BORRADOR: revisa y ajusta con tu criterio antes de presentar.", ""))
        if an.cifras:
            st.markdown("### Las cifras de la noticia, explicadas")
            for c in an.cifras:
                st.markdown(f"- **{c.cifra}**: {c.significado}")
        if an.por_que_podria_importar:
            st.markdown("### Por qué podría importarle a tu negocio")
            st.write(an.por_que_podria_importar)
        if res_n["datos"]:
            st.markdown("### Qué dicen hoy los datos oficiales")
            st.caption("Estas cifras las calcula la app con datos del BCRP; no vienen de la noticia.")
            for d in res_n["datos"]:
                with st.expander(f"{d['nombre']} (serie {d['codigo']})", expanded=True):
                    st.write(" ".join(d["frases"]))
        if an.lo_que_no_dice:
            st.markdown("### Lo que el texto no aclara")
            for x in an.lo_que_no_dice:
                st.markdown(f"- {x}")
        if res_n["malos"]:
            st.warning("Estas cifras de la explicación no aparecen en el texto original; tómalas con cuidado: " + ", ".join(res_n["malos"]))
        else:
            st.success("Todas las cifras de la explicación salen del texto que pegaste.")
        st.caption("La explicación es generada por IA a partir de tu texto. No es asesoría financiera ni verifica si la noticia es cierta.")

# ---------- Chat ----------
with tabs[6]:
    st.subheader("Pregúntale al analista")
    _idx = docs.cargar()
    _nd = len(_idx["documentos"])
    st.caption("Responde con las series oficiales de la app"
               + (f" y con {_nd} documento(s) oficial(es) indexado(s): " + ", ".join(_idx["documentos"]) if _nd else "")
               + ". Si no tiene el dato, te lo dice.")
    modo_rapido = st.toggle("Modo rápido (1 llamada a Gemini por pregunta: más veloz y gasta menos cuota)", value=True,
                            key="modo_rapido")
    with st.expander("Cuéntale de tu negocio (opcional) para que te responda a tu medida"):
        perfil_chat = st.selectbox("Tipo de negocio", ["Prefiero no decir"] + list(PERFILES), key="perfil_chat")
        zona_chat = st.text_input("¿En qué ciudad o región trabajas? (opcional)", key="zona_chat")
        simular = st.checkbox("Quiero que pueda simular mi margen", key="simular_chat")
        if simular:
            cc1, cc2 = st.columns(2)
            m_c = cc1.number_input("Margen actual (%)", 0.0, 90.0, 15.0, 1.0, key="m_c")
            iu_c = cc1.slider("Ventas en dólares (%)", 0, 100, 0, key="iu_c")
            cu_c = cc2.slider("Costos en dólares (%)", 0, 100, 30, key="cu_c")
            ci_c = cc2.slider("Costos en insumos locales (%)", 0, 100 - cu_c, min(40, 100 - cu_c), key="ci_c")
    partes_ctx = []
    if perfil_chat != "Prefiero no decir":
        partes_ctx.append(f"Tipo de negocio: {perfil_chat}")
    if zona_chat.strip():
        partes_ctx.append(f"Zona: {zona_chat.strip()}")
    if simular:
        partes_ctx.append(f"Margen actual {m_c:.0f}%; ventas en dólares {iu_c}%; costos en dólares {cu_c}%; costos en insumos locales {ci_c}%")
    contexto_chat = "\n".join(partes_ctx)

    _clave = clave_api()
    if not _clave:
        st.info("El chat necesita una API key de Gemini (variable `GEMINI_API_KEY` en `.env` o en los secretos de Streamlit).")
    else:
        if "chat" not in st.session_state:
            st.session_state.chat = []
        hist = st.session_state.chat
        for k, msg in enumerate(hist):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg["role"] == "assistant":
                    if msg.get("advertencias"):
                        st.warning("Cifras que no pude verificar en los datos consultados: " + ", ".join(msg["advertencias"]))
                    if msg.get("trazas"):
                        with st.expander("Datos que consulté"):
                            for tr in msg["trazas"]:
                                st.caption(f"{tr['herramienta']} {tr['args'] or ''}")
                                obs = tr["resultado"].get("observaciones") if isinstance(tr["resultado"], dict) else None
                                if obs:
                                    st.line_chart(pd.DataFrame(obs).set_index("fecha")["valor"], height=160)
                                else:
                                    st.json(tr["resultado"], expanded=False)
                    if k == len(hist) - 1 and msg.get("seguimientos"):
                        for j, q in enumerate(msg["seguimientos"]):
                            if st.button(q, key=f"seg_{k}_{j}"):
                                st.session_state.pendiente = q
                                st.rerun()
        if not hist:
            st.caption("Prueba con: 🍰 «Tengo un emprendimiento de postres, ¿cómo me afecta la subida de precios?» · "
                       "🐟 «Tengo una cevichería en Piura, ¿cómo me afecta El Niño?» · "
                       "📦 «Compro mercadería en dólares, ¿cómo está el dólar?» · "
                       "🍇 «Soy agroexportadora de uvas, ¿cómo me afecta El Niño?»")
        pregunta = st.session_state.pop("pendiente", None) or st.chat_input("Escribe tu pregunta")
        if pregunta:
            with st.chat_message("user"):
                st.write(pregunta)
            with st.chat_message("assistant"):
                with st.spinner("Consultando los datos…"):
                    try:
                        from google import genai
                        previo = [{"role": m["role"], "content": m["content"]} for m in hist[-8:]]
                        out = chat.responder(genai.Client(api_key=_clave), previo, pregunta, contexto=contexto_chat, usar_cache=True,
                                           rapido=modo_rapido)
                        hist += [{"role": "user", "content": pregunta},
                                 {"role": "assistant", "content": out["texto"], "seguimientos": out["seguimientos"],
                                  "trazas": out["trazas"], "advertencias": out["advertencias"]}]
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        if type(e).__name__ == "RerunException":
                            raise
                        st.error(f"No se pudo responder: {e}")
        if hist and st.button("Borrar conversación"):
            st.session_state.chat = []
            st.rerun()

    with st.expander("Cómo medimos la calidad del chat (evaluación)"):
        ruta_eval = Path(__file__).resolve().parents[1] / "docs" / "evaluacion.md"
        if ruta_eval.exists():
            st.markdown(ruta_eval.read_text(encoding="utf-8"))
        else:
            st.caption("Ejecuta `python scripts/evaluar.py` para generar el informe.")
