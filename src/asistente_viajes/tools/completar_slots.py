"""Tool de LangChain: completar_slots (RF1, RF2).

Extrae de un mensaje libre los datos de PreferenciasViaje con salida
estructurada del ChatModel, los fusiona de forma no destructiva contra el
estado actual, y genera la pregunta por lo que falta (maximo 2 slots por
turno, nunca repregunta algo que ya esta cargado). Si no falta nada,
devuelve None en el lugar de la pregunta.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.estado import (
    MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO,
    PreferenciasViaje,
    fusionar_preferencias,
)
from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.prompts import PROMPT_EXTRAER_SLOTS, PROMPT_PREGUNTAR_SLOTS_FALTANTES

NOMBRES_LEGIBLES_SLOTS = {
    "destino": "el destino",
    "tipo_destino": "el tipo de destino",
    "intereses": "los intereses",
    "presupuesto": "el presupuesto",
    "fecha_inicio": "la fecha de inicio",
    "fecha_fin": "la fecha de fin",
    "cantidad_personas": "la cantidad de personas",
}


class ArgsCompletarSlots(BaseModel):
    mensaje: str = Field(description="Mensaje en lenguaje natural del usuario")
    estado_actual: PreferenciasViaje = Field(description="Preferencias ya cargadas en la sesion")


def _extraer_slots_del_mensaje(rotador: RotadorClavesGemini, mensaje: str) -> PreferenciasViaje:
    modelo_estructurado = rotador.con_salida_estructurada(PreferenciasViaje)
    prompt = PROMPT_EXTRAER_SLOTS.format(mensaje=mensaje)
    return modelo_estructurado.invoke(prompt)


def _generar_pregunta(rotador: RotadorClavesGemini, slots_a_preguntar: list[str]) -> str:
    nombres = ", ".join(NOMBRES_LEGIBLES_SLOTS[slot] for slot in slots_a_preguntar)
    prompt = PROMPT_PREGUNTAR_SLOTS_FALTANTES.format(slots_faltantes=nombres)
    respuesta = rotador.invocar(prompt)
    return getattr(respuesta, "content", str(respuesta)).strip()


def completar_slots(
    rotador: RotadorClavesGemini, mensaje: str, estado_actual: PreferenciasViaje
) -> tuple[PreferenciasViaje, str | None]:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando un rotador falso."""
    slots_extraidos = _extraer_slots_del_mensaje(rotador, mensaje)
    estado_fusionado = fusionar_preferencias(estado_actual, slots_extraidos)

    faltantes = estado_fusionado.slots_faltantes()
    if not faltantes:
        return estado_fusionado, None

    a_preguntar = faltantes[:MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO]
    pregunta = _generar_pregunta(rotador, a_preguntar)
    return estado_fusionado, pregunta


def crear_tool_completar_slots(rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con el rotador ya inyectado."""

    @tool("completar_slots", args_schema=ArgsCompletarSlots)
    def _tool(mensaje: str, estado_actual: PreferenciasViaje) -> dict:
        """Interpreta un mensaje en lenguaje natural del usuario sobre el
        viaje que quiere hacer (destino, tipo de destino, intereses,
        presupuesto, fechas, cantidad de personas), lo fusiona con las
        preferencias ya cargadas sin pisar nada, y devuelve el estado
        actualizado mas, si todavia falta algo, una pregunta por lo que
        falta (maximo dos datos por vez). Usar esta tool siempre que el
        usuario este describiendo o ajustando su viaje, no para consultas
        puntuales de recomendacion."""
        estado_actualizado, pregunta = completar_slots(rotador, mensaje, estado_actual)
        return {"estado": estado_actualizado.model_dump(), "pregunta": pregunta}

    return _tool
