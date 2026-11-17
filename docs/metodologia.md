# Metodología: termómetro, semáforo y verificador

Todo lo que se describe aquí lo calcula el código (`app/indicators.py`, `app/transform.py`, `app/chat.py`), sin IA. Son criterios de la app: **no son un pronóstico ni una recomendación de inversión.**

## 1. La idea base: comparar cada dato con su propia historia

Un mismo número puede ser bueno o malo según el dato: una inflación de 5 % es alta, pero un crecimiento de 5 % es bueno. Por eso la app no usa umbrales fijos. Para cada indicador calcula **en qué posición está el valor actual dentro de toda su historia** (`transform.percentil_historico`): el porcentaje de meses de la historia que tuvieron un valor menor o igual.

- Ejemplo: la inflación de octubre de 2026 (5.3 %) es mayor o igual que el 86 % de los meses desde 2013. En la app se muestra como “más alto que en 86 de cada 100 meses desde 2013”. Usamos esa frase y no “percentil 86” porque una usuaria no entendió el término ([entrevista 1](research/entrevista-1.md)).
- **Ventajas:**
  - Es transparente, porque se puede explicar en una frase.
  - No depende de supuestos sobre qué valor es “normal”.
  - Funciona igual para todas las series.

## 2. El sentido “malo” de cada dato

Para un negocio, algunos datos preocupan cuando suben y otros cuando bajan:

| Factor | Preocupa si… | Serie (BCRPData / NOAA) |
|---|---|---|
| Precios | sube | Inflación Lima a 12 meses (IPC) |
| Dólar | sube | Tipo de cambio, variación a 12 meses |
| Crecimiento | baja | PBI mensual, variación interanual |
| Pesca | baja | Desembarque de anchoveta, 6 meses vs. el año previo |
| El Niño | sube | Anomalía de temperatura del mar, Niño 1+2 (promedio mensual) |

El **puntaje de preocupación** va de 0 a 100. Es la posición histórica si el dato preocupa al subir, y 100 menos esa posición si preocupa al bajar. **0 es el mejor momento de su historia para un negocio y 100, el peor.**

## 3. Termómetro general (pestaña Resumen)

**Termómetro = promedio simple de los puntajes de los 5 factores.**

- **Por qué pesos iguales:** no tenemos datos de ventas de los usuarios que permitan estimar cuánto pesa cada factor en cada negocio. Cualquier otra ponderación sería arbitraria y más difícil de explicar. El promedio simple es transparente, y el detalle por factor se muestra justo debajo para que cada usuario vea lo que le toca. Ponderar por sector queda en el roadmap.
- **Colores:** verde por debajo de 45, amarillo de 45 a 64 y rojo desde 65.
  - **Por qué 45 y 65:** si todos los factores estuvieran en un punto típico de su historia (alrededor de 50), el termómetro daría cerca de 50 y saldría amarillo, que significa “atención normal”.
  - **Rojo** exige que el promedio esté claramente en la parte mala de la historia. Por ejemplo, 3 de 5 factores en rojo.
  - **Verde** exige que la mayoría esté en la parte buena.
  - Son cortes definidos por nosotros y se pueden cambiar en `app/indicators.py`.
- **Valor al 16/11/2026:** **76, rojo.**
  - El Niño está en 100: el mar está en su máximo desde 1981.
  - La pesca está en 94 y los precios en 86.
  - El dólar (48) y el crecimiento (52) están en zona normal.

## 4. Semáforo por tipo de negocio (pestaña Mi negocio)

Usa el mismo puntaje de preocupación, pero solo con los factores que importan a cada perfil. Por ejemplo, al importador le preocupa que suba el dólar y al exportador, que baje.

- Cada indicador sale **rojo** desde 80 y **amarillo** desde 60. Son umbrales más exigentes que los del termómetro, porque aquí cada color se refiere a un solo dato.
- El **color general del perfil** es rojo si hay 2 o más indicadores en rojo, y amarillo si hay 1 en rojo o 2 en amarillo.

## 5. Verificador de cifras (`chat.cifras_no_respaldadas`)

1. Extrae todos los números de la respuesta de la IA.
2. Busca cada uno en los datos que entregaron las herramientas, con tolerancia por redondeo. Por ejemplo, 5.3 coincide con 5.251.
3. No marca enteros del 0 al 12 (meses, cantidades pequeñas) ni años.
4. Si un número no aparece en los datos, la app lo muestra como advertencia.

**Evaluación** ([evaluacion.md](evaluacion.md)):
- En 9 casos etiquetados detectó las 4 cifras inventadas y dio 0 falsas alarmas.
- En el chat real (8 preguntas de referencia, modo rápido, 16/11/2026) hubo 0 cifras sin respaldo.
- **Limitaciones:** son pocas preguntas y no es una muestra estadística. Además, el verificador comprueba que el número exista en los datos, pero no que se use en el contexto correcto.

## 6. Limitaciones conocidas

- **Pocas observaciones de El Niño:** el promedio de caída de la pesca se calcula con solo 2 episodios pasados (2017 y 2023), así que es una referencia y no un pronóstico.
- **Pesos iguales en el termómetro:** no reflejan cuánto le pesa cada factor a cada negocio en particular (ver la sección 3).
- **Una serie del catálogo sin confirmar:** el ingreso formal real (PN37697PM) todavía no está verificada contra su ficha. No entra en el termómetro, y la app lo avisa si se consulta.

## 7. Cómo se comprobó cada fuente (16/11/2026)

| Dato | Fuente oficial | Cómo se comprobó |
|---|---|---|
| Temperatura del mar, Niño 1+2 | NOAA CPC, archivo semanal [`wksst9120.for`](https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for) | Se descargó el archivo y se comparó con nuestra serie: la columna que usamos es la anomalía (SSTA) de Niño 1+2, y los valores coinciden semana a semana (por ejemplo, +5.6 el 4 nov. y +5.4 el 11 nov. de 2026). |
| Episodios de El Niño (2017, 2023, 2026) | Comunicados del ENFEN (el de 2026 es el N° 20-2026, del 13 nov. 2026) | Son los eventos El Niño costero declarados por el ENFEN. En la serie de NOAA aparecen como picos: +2.3 °C en 2017, +3.5 °C en 2023 y +5.6 °C en 2026. |
| Precios de alimentos (PN01383PM) | API de BCRPData | La API la titula “IPC Alimentos y Bebidas (variación porcentual)”. Es la variación **mensual**, porque los valores cambian de signo de un mes a otro (−0.70 en mayo y +2.20 en marzo de 2026), cosa que no pasa con una variación a 12 meses. |
| Inflación, tipo de cambio, PBI, pesca, tasa de referencia | API de BCRPData | Cada código se abrió en BCRPData para confirmar el nombre y la unidad (`verificada: true` en `data/catalog.json`). |
