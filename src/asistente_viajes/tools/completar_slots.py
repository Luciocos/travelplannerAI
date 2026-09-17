"""Tool de LangChain: completar_slots (RF1, RF2).

Extrae de un mensaje libre los datos de PreferenciasViaje con salida
estructurada del ChatModel, los fusiona de forma no destructiva contra el
estado actual, y arma la pregunta por lo que falta. Desde D-14 esa
pregunta es una sola, con todos los campos faltantes juntos y sus
opciones concretas (ver preguntas.py), armada en Python sin pasar por el
LLM: cero riesgo de que invente una opcion que no existe, y una llamada
menos al LLM por turno. Si no falta nada, devuelve None en el lugar de la
pregunta.

Tambien interpreta descripciones regionales o de caracteristicas del
destino (por ejemplo "un lugar caribeño") contra los destinos piloto de
`data/reference/destinos.json`, en vez de exigir que el usuario nombre la
ciudad. Cuando el destino se infiere asi (no aparece literal en el
mensaje), la pregunta del turno lo confirma explicitamente en vez de
asumirlo en silencio, para no violar la regla de "nada inventado".

tipo_destino ya no se pregunta nunca: en cuanto hay un destino piloto
confirmado se deriva de destinos.json (D-14, ver preguntas.tipo_destino_de).
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.destinos import blurb_caracteristicas_destinos
from asistente_viajes.estado import PreferenciasViaje, fusionar_preferencias
from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.preguntas import armar_pregunta_consolidada, tipo_destino_de
from asistente_viajes.prompts import PROMPT_EXTRAER_SLOTS
from asistente_viajes.texto import normalizar


class ArgsCompletarSlots(BaseModel):
    mensaje: str = Field(description="Mensaje en lenguaje natural del usuario")
    estado_actual: PreferenciasViaje = Field(description="Preferencias ya cargadas en la sesion")


def _extraer_slots_del_mensaje(rotador: RotadorClavesGemini, mensaje: str) -> PreferenciasViaje:
    modelo_estructurado = rotador.con_salida_estructurada(PreferenciasViaje)
    prompt = PROMPT_EXTRAER_SLOTS.format(
        mensaje=mensaje, destinos_piloto=blurb_caracteristicas_destinos()
    )
    return modelo_estructurado.invoke(prompt)


def _destino_fue_inferido(mensaje: str, destino: str) -> bool:
    """True si `destino` no aparece literal en el mensaje: se infirio de
    una descripcion regional o de caracteristicas, no de un nombre de
    ciudad explicito (ver PROMPT_EXTRAER_SLOTS). Insensible a tildes y
    mayusculas."""
    return normalizar(destino) not in normalizar(mensaje)


def completar_slots(
    rotador: RotadorClavesGemini, mensaje: str, estado_actual: PreferenciasViaje
) -> tuple[PreferenciasViaje, str | None]:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando un rotador falso."""
    slots_extraidos = _extraer_slots_del_mensaje(rotador, mensaje)
    estado_fusionado = fusionar_preferencias(estado_actual, slots_extraidos)

    destino_inferido = None
    if (
        estado_fusionado.destino
        and estado_actual.destino is None
        and _destino_fue_inferido(mensaje, estado_fusionado.destino)
    ):
        destino_inferido = estado_fusionado.destino

    if estado_fusionado.tipo_destino is None:
        derivado = tipo_destino_de(estado_fusionado.destino)
        if derivado is not None:
            estado_fusionado = estado_fusionado.model_copy(update={"tipo_destino": derivado})

    faltantes = estado_fusionado.slots_faltantes()
    confirmacion = (
        f"Perfecto, entonces {destino_inferido}. Avíseme si no es así."
        if destino_inferido
        else None
    )

    if not faltantes:
        return estado_fusionado, confirmacion

    pregunta = armar_pregunta_consolidada(faltantes)
    pregunta_completa = f"{confirmacion} {pregunta}" if confirmacion else pregunta
    return estado_fusionado, pregunta_completa


def crear_tool_completar_slots(rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con el rotador ya inyectado."""

    @tool("completar_slots", args_schema=ArgsCompletarSlots)
    def _tool(mensaje: str, estado_actual: PreferenciasViaje) -> dict:
        """Interpreta un mensaje en lenguaje natural del usuario sobre el
        viaje que quiere hacer (destino, intereses, presupuesto, fechas,
        cantidad de personas), lo fusiona con las preferencias ya
        cargadas sin pisar nada, y devuelve el estado actualizado mas, si
        todavia falta algo, una sola pregunta consolidada por todo lo que
        falta. Usar esta tool siempre que el usuario este describiendo o
        ajustando su viaje, no para consultas puntuales de recomendacion."""
        estado_actualizado, pregunta = completar_slots(rotador, mensaje, estado_actual)
        return {"estado": estado_actualizado.model_dump(), "pregunta": pregunta}

    return _tool
