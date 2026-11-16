"""Indexa los documentos de data/docs/ (PDF, TXT, MD) para que el chat pueda consultarlos.

    python scripts/indexar_docs.py
Luego haz commit de data/docs_index.json (y de los documentos, si su licencia lo permite).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import docs  # noqa: E402


def main() -> int:
    docs.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    idx = docs.indexar()
    if not idx["fragmentos"]:
        print("No se encontró texto. Pon PDF, TXT o MD en data/docs/ (los PDF escaneados no tienen texto extraíble).")
        return 1
    docs.guardar(idx)
    for d, n in idx["documentos"].items():
        print(f"{d}: {n} fragmentos")
    print(f"Índice guardado en {docs.INDICE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
