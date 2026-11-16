# Herramientas del curso dentro del producto (para la parte 8 del README)

| Sesión | Herramienta | Dónde está en el producto |
|---|---|---|
| 03 | APIs | `app/bcrp.py` y `scripts/fetch_bcrp.py` descargan las series desde la API de BCRPData; `scripts/fetch_noaa.py` baja la temperatura del mar de NOAA |
| 05 | Dashboards | `app/streamlit_app.py`: 7 pestañas con gráficos interactivos (Plotly) |
| 06 | Folium | Pestaña "Mapa y sensibilidad": mapa de regiones pesqueras (`app/geo.py`) |
| 08 | LLM con salidas estructuradas y RAG | `app/noticia.py` (explicación de noticias en JSON validado con pydantic); `app/chat.py` + `app/data.py::buscar_fichas` (recuperación sobre las fichas) |
| 08 (RAG con documentos) | Fragmentos con cita de página | `app/docs.py`, `scripts/indexar_docs.py`: indexa reportes oficiales (PDF/TXT) y el chat los cita. Extrae texto con pypdf; los PDF escaneados requerirían OCR |
| 12 | Evaluación | `app/evaluacion.py`, `scripts/evaluar.py` -> `docs/evaluacion.md`; despliegue en `docs/DESPLIEGUE.md` |
| 15 | Texto a voz | `app/voz.py`: botón "Escuchar" en Series y Explícame una noticia |
| 16 | Skills de Claude Code | `.claude/skills/actualizando-series/SKILL.md` |
