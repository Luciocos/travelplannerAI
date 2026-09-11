"""Tool de LangChain: completar_slots (RF1, RF2).

Extrae de un mensaje libre los datos de PreferenciasViaje con salida
estructurada del ChatModel, los fusiona de forma no destructiva contra el
estado actual, y genera la pregunta por lo que falta (maximo 2 slots por
turno, nunca repregunta algo que ya esta cargado). Si no falta nada,
devuelve None en el lugar de la pregunta.

Tambien interpreta descripciones regionales o de caracteristicas del
destino (por ejemplo "un lugar caribeño") contra los destinos piloto de
`data/reference/destinos.json`, en vez de exigir que el usuario nombre la
ciudad. Cuando el destino se infiere asi (no aparece literal en el
mensaje), la pregunta del turno lo confirma explicitamente en vez de
asumirlo en silencio, para no violar la regla de "nada inventado".
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.destinos import cargar_destinos_piloto
from asistente_viajes.estado import (
    MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO,
    PreferenciasViaje,
    fusionar_preferencias,
)
from asistente_viajes.llm import RotadorClavesGemini, contenido_texto
from asistente_viajes.prompts import (
    NOTA_CONFIRMAR_DESTINO_INFERIDO,
    PROMPT_CONFIRMAR_DESTINO_INFERIDO,
    PROMPT_EXTRAER_SLOTS,
    PROMPT_PREGUNTAR_SLOTS_FALTANTES,
)
from asistente_viajes.texto import normalizar

NOMBRES_LEGIBLES_SLOTS = {
    "destino": "el destino",
    "tipo_destino": "el tipo de destino que busca (por ejemplo playa, ciudad, montaña o naturaleza, no el nombre del lugar)",
    "intereses": "los intereses",
    "presupuesto": "el presupuesto",
    "fecha_inicio": "la fecha de inicio",
    "fecha_fin": "la fecha de fin",
    "cantidad_personas": "la cantidad de personas",
}


class ArgsCompletarSlots(BaseModel):
    mensaje: str = Field(description="Mensaje en lenguaje natural del usuario")
    estado_actual: PreferenciasViaje = Field(description="Preferencias ya cargadas en la sesion")


def _blurb_destinos_piloto() -> str:
    """Para el prompt de extraccion: nombre y caracteristicas de cada
    destino piloto, asi el LLM puede mapear una descripcion regional a
    uno de ellos en vez de exigir el nombre exacto de la ciudad."""
    destinos = cargar_destinos_piloto()
    lineas = [
        f"{nombre}: {', '.join(datos.get('caracteristicas', []))}"
        for nombre, datos in destinos.items()
    ]
    return "\n  ".join(lineas)


def _extraer_slots_del_mensaje(rotador: RotadorClavesGemini, mensaje: str) -> PreferenciasViaje:
    modelo_estructurado = rotador.con_salida_estructurada(PreferenciasViaje)
    prompt = PROMPT_EXTRAER_SLOTS.format(mensaje=mensaje, destinos_piloto=_blurb_destinos_piloto())
    return modelo_estructurado.invoke(prompt)


def _destino_fue_inferido(mensaje: str, destino: str) -> bool:
    """True si `destino` no aparece literal en el mensaje: se infirio de
    una descripcion regional o de caracteristicas, no de un nombre de
    ciudad explicito (ver PROMPT_EXTRAER_SLOTS). Insensible a tildes y
    mayusculas."""
    return normalizar(destino) not in normalizar(mensaje)


def _generar_pregunta(
    rotador: RotadorClavesGemini, slots_a_preguntar: list[str], destino_a_confirmar: str | None = None
) -> str:
    nombres = ", ".join(NOMBRES_LEGIBLES_SLOTS[slot] for slot in slots_a_preguntar)
    nota = (
        NOTA_CONFIRMAR_DESTINO_INFERIDO.format(destino=destino_a_confirmar)
        if destino_a_confirmar
        else ""
    )
    prompt = PROMPT_PREGUNTAR_SLOTS_FALTANTES.format(slots_faltantes=nombres, nota_destino_inferido=nota)
    respuesta = rotador.invocar(prompt)
    return contenido_texto(respuesta)


def _confirmar_destino_inferido(rotador: RotadorClavesGemini, destino: str) -> str:
    prompt = PROMPT_CONFIRMAR_DESTINO_INFERIDO.format(destino=destino)
    respuesta = rotador.invocar(prompt)
    return contenido_texto(respuesta)


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

    faltantes = estado_fusionado.slots_faltantes()
    if not faltantes:
        pregunta = (
            _confirmar_destino_inferido(rotador, destino_inferido) if destino_inferido else None
        )
        return estado_fusionado, pregunta

    a_preguntar = faltantes[:MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO]
    pregunta = _generar_pregunta(rotador, a_preguntar, destino_inferido)
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
