---
name: actualizando-series
description: Actualiza las series del Termómetro BCRP desde BCRPData, valida que los datos sean coherentes y prepara el commit. Úsala cuando haya que refrescar datos o agregar una serie nueva al catálogo.
---

# Actualizando las series del Termómetro

1. Si hay una serie nueva, agrégala a `data/catalog.json` con `id`, `code`, `nombre`, `tema`, `frecuencia`, `unidad`, `transformacion` y `verificada: false`. Nunca inventes un código: pídelo al usuario desde la página de BCRPData.
2. Ejecuta `python scripts/fetch_bcrp.py` (o `--only <id>`). Revisa que no haya fallas y que la fecha del último dato tenga sentido.
3. Para la temperatura del mar, ejecuta `python scripts/fetch_noaa.py` y compara las primeras filas del CSV con el archivo original.
4. Pon `verificada: true` solo si el usuario confirmó nombre y unidad en la página de la serie.
5. Corre `python -m pytest -q`. Si falla algo, no hagas commit: explica qué falló.
6. Corre `python scripts/evaluar.py` para refrescar `docs/evaluacion.md`.
7. Revisa con `git status` que no aparezcan `.env`, `.venv` ni `__pycache__`. Haz commit de `data/series/` y del catálogo.

Reglas: los números los calcula el código, nunca el modelo; no subas claves; si una serie no se puede descargar, dilo y usa el plan B (`--from-csv`).
