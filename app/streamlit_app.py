"""Termómetro BCRP + El Niño. Ejecutar con:  streamlit run app/streamlit_app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from app import periodista  # noqa: E402
from app.data import analitica, catalogo, ficha, info  # noqa: E402
from app.indicators import PERFILES, evaluar  # noqa: E402
from app.data import SERIES_DIR  # noqa: E402

st.set_page_config(page_title="Termómetro BCRP + El Niño", layout="wide")
st.title("Termómetro BCRP + El Niño")
st.caption("Datos oficiales del BCRP. Los números los calcula el código; los textos son explicativos y no son pronósticos.")

EMOJI = {"rojo": "🔴", "amarillo": "🟡", "verde": "🟢", "gris": "⚪"}


def disponibles() -> list[dict]:
    return [s for s in catalogo() if (SERIES_DIR / f"{s['id']}.csv").exists()]


def grafico(sid: str, desde: str | None = None):
    df = analitica(sid)
    if desde:
        df = df[df["fecha"] >= pd.Timestamp(desde)]
    meta = info(sid)
    fig = px.line(df, x="fecha", y="valor", title=meta["nombre"], labels={"valor": meta["unidad"], "fecha": ""})
    st.plotly_chart(fig, use_container_width=True)
    ult = df.dropna().iloc[-1]
    st.caption(f"Último dato: {ult['fecha'].date()} = {ult['valor']:.2f}  |  Serie BCRPData {meta['code']}")
    if not meta.get("verificada"):
        st.warning("Esta serie aún no está verificada contra su página en BCRPData.")


tab1, tab2, tab3, tab4, tab5 = st.tabs(["Series", "El Niño", "Mi negocio", "Periodista", "Chat"])

with tab1:
    series = disponibles()
    if not series:
        st.error("No hay datos descargados. Ejecuta: python scripts/fetch_bcrp.py")
    else:
        temas = sorted({s["tema"] for s in series})
        tema = st.selectbox("Tema", temas, format_func=lambda t: t.replace("_", " ").capitalize())
        opciones = [s for s in series if s["tema"] == tema]
        elegida = st.selectbox("Serie", opciones, format_func=lambda s: s["nombre"])
        desde = st.slider("Desde el año", 2012, 2026, 2020)
        grafico(elegida["id"], f"{desde}-01-01")
        texto = ficha(elegida["id"])
        st.markdown(texto if texto else "_Ficha pendiente para esta serie._")

with tab2:
    st.subheader("Qué es El Niño Costero y por qué importa a la economía")
    st.markdown(
        "El Niño Costero es un calentamiento anómalo del mar frente a la costa de Perú. Las autoridades lo siguen con "
        "alertas del ENFEN. Afecta a la economía por tres canales: **pesca** (la anchoveta se desplaza o escasea y cae la "
        "producción de harina y aceite), **agro** (lluvias intensas o calor excesivo dañan cultivos) y **precios de alimentos** "
        "(menos oferta puede subir precios).")
    st.info("Pendiente: superponer la anomalía de temperatura del mar (Niño 1+2, NOAA) sobre estos gráficos.")
    for sid in ("anchoveta_total", "harina_precio", "pbi_pesca_yoy"):
        if (SERIES_DIR / f"{sid}.csv").exists():
            grafico(sid, "2012-01-01")
            st.markdown(ficha(sid) or "")
    st.caption("Limitación: la segunda temporada de anchoveta solo se verá en estos datos cuando se publiquen esos meses. "
               "Que dos series se muevan juntas no prueba causalidad.")

with tab3:
    perfil = st.selectbox("¿Cuál es tu negocio?", list(PERFILES))
    res = evaluar(perfil)
    st.markdown(f"### Exposición general: {EMOJI[res['general']]} {res['general'].upper()}")
    for ind in res["indicadores"]:
        st.markdown(f"{EMOJI[ind['color']]} **{ind['nombre']}**: {ind['razon']}")
    st.caption(res["advertencia"])

with tab4:
    hs = periodista.hechos()
    base = periodista.nota_plantilla(hs)
    texto = st.text_area("Nota (puedes editarla)", base, height=200)
    if st.button("Verificar cifras"):
        malos = periodista.verificar_numeros(texto, hs)
        if malos:
            st.error(f"Cifras que no provienen de los datos: {', '.join(malos)}")
        else:
            st.success("Todas las cifras coinciden con los datos del BCRP.")

with tab5:
    st.info("El chat con IA se conecta en la siguiente fase. Solo podrá consultar las series del catálogo.")
