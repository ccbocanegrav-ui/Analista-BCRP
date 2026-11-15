"""Plan de exposición: ideas de acción según el semáforo. Son ideas para conversar con un asesor, no recomendaciones."""
from __future__ import annotations

AVISO = ("Estas son ideas generales para ordenar tu reflexión, no son una recomendación financiera ni legal. "
         "Valida cada una con tu contador, tu banco o un asesor, según tu caso.")

# clave de indicador -> {sentido adverso: [(horizonte, acción)]}
ACCIONES = {
    "tc_var12": {
        "alza": [("Esta semana", "Revisa qué parte de tus costos y deudas está en dólares y cuánto pesa en tu margen (usa el simulador de abajo)."),
                 ("Próximos 3 meses", "Negocia con tu proveedor un precio fijo por 60 a 90 días o cotizar en soles."),
                 ("Próximos 3 meses", "Pregunta a tu banco por coberturas cambiarias y por su costo antes de decidir.")],
        "baja": [("Esta semana", "Si vendes en dólares, calcula con qué tipo de cambio te sigue saliendo rentable cada contrato."),
                 ("Próximos 3 meses", "Evalúa vender más al mercado local o fijar con tus clientes un precio mínimo en soles.")],
    },
    "inflacion": {
        "alza": [("Esta semana", "Anota cuáles de tus insumos subieron más en los últimos meses y cuánto pesan en tu costo."),
                 ("Próximos 3 meses", "Revisa tus precios de venta: ¿puedes ajustarlos por tramos pequeños y comunicados a tus clientes?"),
                 ("Si empeora", "Busca un segundo proveedor para tus insumos más críticos.")],
    },
    "pbi_yoy": {
        "baja": [("Próximos 3 meses", "Si la economía se enfría, cuida tu caja: reduce inventarios lentos y revisa plazos de cobro."),
                 ("Si empeora", "Prepara un plan de gastos mínimos y qué podrías postergar sin perder clientes.")],
    },
    "harina_precio": {
        "baja": [("Próximos 3 meses", "Si tus ingresos dependen del precio de la harina, calcula con qué precio por tonelada cubres tus costos."),
                 ("Si empeora", "Evalúa vender parte de tu producción por contrato a precio fijo.")],
    },
    "anchoveta_6m": {
        "baja": [("Esta semana", "Revisa si tus ingresos dependen de una sola temporada de pesca y cuántos meses de costos fijos puedes cubrir."),
                 ("Próximos 3 meses", "Conversa con tus proveedores y trabajadores sobre un plan por si la temporada se retrasa o se acorta."),
                 ("Si empeora", "Pregunta por seguros o apoyos disponibles para tu actividad ante eventos climáticos.")],
    },
    "pbi_pesca": {
        "baja": [("Próximos 3 meses", "Si compras o vendes productos del mar, guarda una lista de proveedores alternativos de otras zonas.")],
    },
}

SENALES = {
    "tc_var12": "Mira el promedio mensual del dólar y su variación frente al año anterior.",
    "inflacion": "Mira la inflación a 12 meses y los precios de alimentos.",
    "pbi_yoy": "Mira el crecimiento mensual de la economía durante varios meses seguidos.",
    "harina_precio": "Mira el precio de la harina de pescado.",
    "anchoveta_6m": "Mira los desembarques de anchoveta de los últimos 6 meses frente al año pasado.",
    "pbi_pesca": "Mira el crecimiento mensual de la pesca.",
}


def construir(evaluacion: dict) -> dict:
    """evaluacion: resultado de indicators.evaluar(). Devuelve acciones por horizonte y señales a vigilar."""
    acciones: dict[str, list[dict]] = {"Esta semana": [], "Próximos 3 meses": [], "Si empeora": []}
    vigilar = []
    for ind in evaluacion["indicadores"]:
        if ind["color"] in ("rojo", "amarillo"):
            for horizonte, texto in ACCIONES.get(ind["clave"], {}).get(ind["sentido"], []):
                if ind["color"] == "amarillo" and horizonte == "Si empeora":
                    continue
                acciones[horizonte].append({"texto": texto, "indicador": ind["nombre"], "color": ind["color"]})
        if ind["color"] != "gris" and ind.get("umbral_rojo") is not None:
            vigilar.append({"indicador": ind["nombre"], "actual": ind["valor"], "unidad": ind["unidad"],
                            "umbral_amarillo": ind["umbral_amarillo"], "umbral_rojo": ind["umbral_rojo"],
                            "sentido": ind["sentido"], "color": ind["color"], "senal": SENALES.get(ind["clave"], "")})
    return {"acciones": acciones, "vigilar": vigilar, "aviso": AVISO}
