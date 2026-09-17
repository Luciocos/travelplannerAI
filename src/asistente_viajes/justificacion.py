"""Justificacion de recomendaciones en una sola llamada al LLM (RF3, RF4).

Antes, recomendar_actividades/recomendar_locales hacian una llamada al LLM
POR CADA resultado recuperado (k llamadas). Ademas de multiplicar la
latencia (ver P-06 en DIFICULTADES.md), cuando el texto de un resultado no
alcanzaba para justificarlo el LLM igual devolvia una linea de "no se
puede justificar" que se mostraba como si fuera la recomendacion, una
respuesta confusa. Con una sola llamada por lote, el LLM marca cada
resultado como relevante o no, y los no relevantes se descartan antes de
mostrarle nada al usuario.
"""

from __future__ import annotations

from pydantic import BaseModel

from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.prompts import PROMPT_JUSTIFICAR_RECOMENDACIONES_LOTE


class ItemJustificado(BaseModel):
    indice: int
    relevante: bool
    justificacion: str = ""


class LoteJustificado(BaseModel):
    items: list[ItemJustificado]


def justificar_lote(
    rotador: RotadorClavesGemini, intereses_o_consulta: str, textos: list[str]
) -> dict[int, ItemJustificado]:
    """Una sola llamada estructurada que evalua y justifica todos los
    textos de una vez. Devuelve un dict indice -> ItemJustificado (solo
    los indices que el LLM devolvio; si faltara alguno se trata como no
    relevante, ver los tools que consumen esto)."""
    if not textos:
        return {}

    lugares = "\n\n".join(f"[{indice}] {texto}" for indice, texto in enumerate(textos))
    prompt = PROMPT_JUSTIFICAR_RECOMENDACIONES_LOTE.format(
        intereses_o_consulta=intereses_o_consulta, lugares=lugares
    )
    modelo_estructurado = rotador.con_salida_estructurada(LoteJustificado)
    resultado = modelo_estructurado.invoke(prompt)
    return {item.indice: item for item in resultado.items}
