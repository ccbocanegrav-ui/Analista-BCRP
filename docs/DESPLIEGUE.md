# Cómo publicar la app con un URL público (Streamlit Community Cloud)

Requisitos previos: repo **público** en GitHub, con `requirements.txt` y la carpeta `data/series/` con los CSV subidos.

1. Entra a https://share.streamlit.io e inicia sesión con **la cuenta de GitHub donde está el repo**.
2. Pulsa **Create app** → **Deploy a public app from GitHub**.
3. Repository: `tu-usuario/Analista-BCRP` · Branch: `main` · Main file path: `app/streamlit_app.py`.
4. Abre **Advanced settings**:
   - Python version: 3.12 o 3.13.
   - Secrets (pega esto, con tu clave real):
     ```toml
     GEMINI_API_KEY = "tu_clave_de_gemini"
     ```
5. **Deploy**. En unos minutos tendrás un URL del tipo `https://nombre.streamlit.app`.
6. Abre el URL en una ventana de incógnito para confirmar que es público (sin pedir login).

Cuidados:
- La clave **nunca** va en el repo. Solo en Secrets o en tu `.env` local (ya ignorado por `.gitignore`).
- Ponle un tope de gasto a la clave en la Google AI Studio (revisa los límites de uso de tu clave).
- Las apps gratuitas se "duermen" tras un tiempo sin visitas: ábrela 5 minutos antes de la demo para despertarla.
- Si cambias los datos (`python scripts/fetch_bcrp.py`), haz commit y push de `data/series/`; la app se redespliega sola.
- Respaldo para la demo en vivo: ten la app corriendo local (`streamlit run app/streamlit_app.py`) y el video de 60–90 s grabado.
