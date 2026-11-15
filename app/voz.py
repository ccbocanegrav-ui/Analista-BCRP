"""Texto a voz (sesión 15 del curso: del texto a tu voz). Lee resúmenes en voz alta para quien prefiere escuchar.

Usa gTTS (necesita internet al generar el audio). Si se quiere usar otra voz, basta cambiar `sintetizar`.
"""
from __future__ import annotations

import io
import re


def limpiar(texto: str) -> str:
    texto = re.sub(r"[*_#>`]", "", texto)
    texto = texto.replace("US$", "dólares").replace("S/", "soles").replace("%", " por ciento")
    return re.sub(r"\s+", " ", texto).strip()


def sintetizar(texto: str, idioma: str = "es", max_caracteres: int = 1200) -> bytes:
    """Devuelve audio MP3. Lanza RuntimeError con mensaje claro si no se puede generar."""
    try:
        from gtts import gTTS
    except ImportError as e:
        raise RuntimeError("Falta instalar gTTS (pip install gTTS)") from e
    t = limpiar(texto)[:max_caracteres]
    if not t:
        raise RuntimeError("No hay texto para leer")
    buf = io.BytesIO()
    try:
        gTTS(t, lang=idioma).write_to_fp(buf)
    except Exception as e:  # noqa: BLE001  (errores de red u otros del servicio)
        raise RuntimeError(f"No se pudo generar el audio: {e}") from e
    return buf.getvalue()
