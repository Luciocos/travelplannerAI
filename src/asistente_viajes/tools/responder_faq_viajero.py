"""Tool de LangChain: responder_faq_viajero (RF9, extension).

Sobre el corpus curado de FAQ (seguridad, estafas comunes, costumbres). A
diferencia de recomendar_locales/recomendar_actividades (una recomendacion
por lugar), aca el usuario hizo UNA pregunta: se sintetiza UNA respuesta
combinando los temas recuperados en una sola llamada al LLM, en vez de
devolver una respuesta separada por tema (antes, cuando ningun tema tenia
la info pedida, esto se veia como la misma negativa repetida k veces)."""

from __future__ import annotations

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.prompts import PROMPT_RESPONDER_FAQ_VIAJERO
from asistente_viajes.recuperacion.faq import buscar_faq


class RespuestaFaq(BaseModel):
    respondida: bool
    respuesta: str
    temas_usados: list[str] = Field(default_factory=list)


class ArgsResponderFaqViajero(BaseModel):
    destino: str = Field(description="Destino confirmado del viaje")
    consulta: str = Field(
        description="Pregunta del usuario sobre seguridad, estafas o costumbres del destino"
    )
    k: int = Field(default=3, description="Cantidad maxima de temas a recuperar")


def _sintetizar(
    rotador: RotadorClavesGemini, consulta: str, temas: list[tuple[str, str]]
) -> RespuestaFaq:
    temas_recuperados = "\n\n".join(f"### {tema}\n{texto}" for tema, texto in temas)
    prompt = PROMPT_RESPONDER_FAQ_VIAJERO.format(
        consulta=consulta, temas_recuperados=temas_recuperados
    )
    modelo_estructurado = rotador.con_salida_estructurada(RespuestaFaq)
    return modelo_estructurado.invoke(prompt)


def responder_faq_viajero(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    destino: str,
    consulta: str,
    k: int = 3,
) -> RespuestaFaq:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando conexion y rotador falsos. Devuelve una unica respuesta
    sintetizada, no una lista por tema."""
    resultados = buscar_faq(conexion, destino=destino, consulta=consulta, k=k)
    if not resultados:
        return RespuestaFaq(
            respondida=False,
            respuesta="No tengo información sobre seguridad, estafas o costumbres para esa consulta en este destino.",
        )
    temas = [(resultado.nombre or "Tema sin nombre", resultado.texto) for resultado in resultados]
    return _sintetizar(rotador, consulta, temas)


def crear_tool_responder_faq_viajero(conexion: psycopg.Connection, rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con la conexion y el rotador ya inyectados."""

    @tool("responder_faq_viajero", args_schema=ArgsResponderFaqViajero)
    def _tool(destino: str, consulta: str, k: int = 3) -> dict:
        """Responde preguntas puntuales del viajero sobre seguridad,
        estafas comunes o costumbres locales de un destino ya confirmado.
        Usar esta tool cuando el usuario pregunta si un lugar es seguro,
        que estafas evitar, cuanto dejar de propina, o cosas similares de
        seguridad/costumbres, no para recomendaciones de actividades o
        comercios."""
        return responder_faq_viajero(conexion, rotador, destino, consulta, k).model_dump()

    return _tool
