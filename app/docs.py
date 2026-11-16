"""Documentos de apoyo (RAG, sesiones 08 y 10): reportes del BCRP, comunicados del ENFEN, etc.

Se colocan PDF, TXT o MD en data/docs/, se indexan con scripts/indexar_docs.py y el chat los consulta con citas
(documento y página). Así el chat puede explicar el "por qué" y las proyecciones oficiales, no solo las series.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "docs"
INDICE = ROOT / "data" / "docs_index.json"
TAM, SOLAPE = 900, 150
_STOP = {"para", "como", "este", "esta", "esto", "pero", "porque", "sobre", "entre", "desde", "hasta", "donde", "cuando",
         "tiene", "tienen", "ser", "los", "las", "del", "con", "una", "uno", "por", "que", "qué", "más", "muy"}


def _tokens(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-záéíóúñ0-9]{3,}", t.lower()) if w not in _STOP]


def partir(texto: str, tam: int = TAM, solape: int = SOLAPE) -> list[str]:
    """Parte un texto en fragmentos con solape, cortando en espacios."""
    t = re.sub(r"\s+", " ", texto).strip()
    out, i = [], 0
    while i < len(t):
        fin = min(len(t), i + tam)
        if fin < len(t):
            corte = t.rfind(" ", i + tam // 2, fin)
            fin = corte if corte > 0 else fin
        out.append(t[i:fin].strip())
        if fin >= len(t):
            break
        i = max(fin - solape, i + 1)
    return [c for c in out if len(c) > 60]


def leer_paginas(ruta: Path) -> list[tuple[int, str]]:
    """Devuelve [(página, texto)]. PDF con pypdf; TXT/MD como una sola 'página' por bloque de ~3000 caracteres."""
    if ruta.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(str(ruta)).pages)]
    txt = ruta.read_text(encoding="utf-8", errors="ignore")
    return [(i // 3000 + 1, txt[i:i + 3000]) for i in range(0, len(txt), 3000)]


def indexar(docs_dir: Path = DOCS_DIR) -> dict:
    fragmentos, resumen = [], {}
    for ruta in sorted(docs_dir.glob("*")):
        if ruta.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue
        n = 0
        for pag, texto in leer_paginas(ruta):
            for frag in partir(texto):
                fragmentos.append({"doc": ruta.stem, "pagina": pag, "texto": frag})
                n += 1
        resumen[ruta.stem] = n
    return {"fragmentos": fragmentos, "documentos": resumen}


def guardar(indice: dict, destino: Path = INDICE) -> None:
    destino.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")


def cargar(ruta: Path = INDICE) -> dict:
    if not ruta.exists():
        return {"fragmentos": [], "documentos": {}}
    return json.loads(ruta.read_text(encoding="utf-8"))


def buscar(consulta: str, k: int = 4, indice: dict | None = None) -> list[dict]:
    """Recuperación por relevancia de palabras (TF-IDF simple). Devuelve los k fragmentos más relevantes."""
    idx = indice if indice is not None else cargar()
    frs = idx["fragmentos"]
    if not frs:
        return []
    q = set(_tokens(consulta))
    toks = [Counter(_tokens(f["texto"])) for f in frs]
    df = Counter(w for c in toks for w in c)
    n = len(frs)
    puntajes = []
    for f, c in zip(frs, toks):
        s = sum((1 + math.log(c[w])) * math.log(1 + n / df[w]) for w in q if w in c)
        if s > 0:
            puntajes.append((s, f))
    puntajes.sort(key=lambda x: -x[0])
    return [{"fuente": f"{f['doc']}, p. {f['pagina']}", "texto": f["texto"], "puntaje": round(s, 2)} for s, f in puntajes[:k]]
