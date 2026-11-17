"""Corre la evaluación y escribe docs/evaluacion.md.

    python scripts/evaluar.py              # solo el verificador (sin API)
    python scripts/evaluar.py --chat       # además el chat real (necesita GEMINI_API_KEY y datos descargados)
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import evaluacion  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chat", action="store_true")
    ap.add_argument("--rapido", action="store_true", help="evalúa el modo rápido (1 llamada por pregunta)")
    args = ap.parse_args()
    verif = evaluacion.evaluar_verificador()
    res = None
    if args.chat:
        from dotenv import load_dotenv
        from google import genai
        load_dotenv()
        if not os.environ.get("GEMINI_API_KEY"):
            print("Falta GEMINI_API_KEY"); return 1
        res = evaluacion.evaluar_chat(genai.Client(), rapido=args.rapido)
    md = evaluacion.informe_markdown(verif, res)
    (ROOT / "docs" / "evaluacion.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
