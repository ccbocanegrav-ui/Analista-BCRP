"""Salidas estructuradas (sesión 08) con Gemini: el modelo redacta la nota, pero debe entregar un JSON con esquema fijo.

Flujo: el código calcula los hechos -> el modelo los redacta en el esquema NotaPeriodistica (response_schema)
-> pydantic valida -> el verificador revisa que cada cifra salga de los hechos.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app import periodista
from app.chat import MODELO


class Punto(BaseModel):
    texto: str = Field(description="Frase corta en lenguaje simple que usa SOLO los hechos entregados")
    cifra: float = Field(description="Cifra principal de la frase, tal cual aparece en los hechos")
    serie: str = Field(description="Código BCRPData de la serie de donde sale la cifra")


class NotaPeriodistica(BaseModel):
    titular: str = Field(description="Titular de máximo 120 caracteres")
    bajada: str = Field(description="Una o dos frases que resumen la nota (máximo 300 caracteres)")
    puntos: list[Punto] = Field(description="Entre 1 y 6 puntos")
    fuente: str = Field(description="Fuente de los datos")

    @field_validator("titular")
    @classmethod
    def _titular(cls, v):
        if not v.strip() or len(v) > 120:
            raise ValueError("titular vacío o de más de 120 caracteres")
        return v

    @field_validator("puntos")
    @classmethod
    def _puntos(cls, v):
        if not 1 <= len(v) <= 6:
            raise ValueError("debe haber entre 1 y 6 puntos")
        return v


SISTEMA = ("Eres un redactor económico para emprendedores que no saben de economía. Redacta una nota breve usando EXCLUSIVAMENTE "
           "los hechos que recibes: no agregues cifras, fechas ni causas que no estén en ellos. Palabras simples.")


def generar(cliente, hs: list[dict], modelo: str = MODELO) -> tuple[NotaPeriodistica, list[str]]:
    """Devuelve (nota validada, cifras no respaldadas). Lanza ValueError si el modelo no cumple el esquema."""
    from google.genai import types
    hechos_txt = "\n".join(f"- {h['texto']} (serie {h['fuente']})" for h in hs)
    resp = cliente.models.generate_content(
        model=modelo, contents=f"Hechos:\n{hechos_txt}",
        config=types.GenerateContentConfig(system_instruction=SISTEMA, response_mime_type="application/json",
                                           response_schema=NotaPeriodistica, max_output_tokens=1500))
    if not (resp.text or "").strip():
        raise ValueError("El modelo no devolvió la nota estructurada")
    nota = NotaPeriodistica.model_validate_json(resp.text)
    texto = " ".join([nota.titular, nota.bajada, *[p.texto for p in nota.puntos]])
    malos = periodista.verificar_numeros(texto, hs)
    permitidas = {round(abs(v), 3) for h in hs for v in h["valores"]}
    for p in nota.puntos:
        if not any(abs(abs(p.cifra) - v) <= 0.0006 or abs(abs(p.cifra) - v) <= 0.05 for v in permitidas):
            malos.append(str(p.cifra))
    return nota, malos


def a_texto(nota: NotaPeriodistica) -> str:
    cuerpo = "\n".join(f"- {p.texto}" for p in nota.puntos)
    return f"{nota.titular}\n\n{nota.bajada}\n\n{cuerpo}\n\nFuente: {nota.fuente}"
