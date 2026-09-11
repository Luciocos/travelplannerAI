"""Tool de LangChain: responder_faq_viajero (RF9, extension).

Mismo patron que recomendar_locales/recomendar_actividades pero sobre el
corpus curado de FAQ (seguridad, estafas comunes, costumbres). La
respuesta se genera solo sobre el texto recuperado, sin agregar datos.
"""

from __future__ import annotations

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.llm import RotadorClavesGemini, contenido_texto
from asistente_viajes.prompts import PROMPT_RESPONDER_FAQ_VIAJERO
from asistente_viajes.recuperacion.faq import buscar_faq


class RespuestaFaq(BaseModel):
    tema: str | None
    categoria: str | None
    respuesta: str


class ArgsResponderFaqViajero(BaseModel):
    destino: str = Field(description="Destino confirmado del viaje")
    consulta: str = Field(
        description="Pregunta del usuario sobre seguridad, estafas o costumbres del destino"
    )
    k: int = Field(default=3, description="Cantidad maxima de temas a recuperar")


def _responder(rotador: RotadorClavesGemini, texto: str, consulta: str) -> str:
    prompt = PROMPT_RESPONDER_FAQ_VIAJERO.format(consulta=consulta, texto_recuperado=texto)
    respuesta = rotador.invocar(prompt)
    return contenido_texto(respuesta)


def responder_faq_viajero(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    destino: str,
    consulta: str,
    k: int = 3,
) -> list[RespuestaFaq]:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando conexion y rotador falsos."""
    resultados = buscar_faq(conexion, destino=destino, consulta=consulta, k=k)
    return [
        RespuestaFaq(
            tema=resultado.nombre,
            categoria=resultado.categoria,
            respuesta=_responder(rotador, resultado.texto, consulta),
        )
        for resultado in resultados
    ]


def crear_tool_responder_faq_viajero(conexion: psycopg.Connection, rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con la conexion y el rotador ya inyectados."""

    @tool("responder_faq_viajero", args_schema=ArgsResponderFaqViajero)
    def _tool(destino: str, consulta: str, k: int = 3) -> list[dict]:
        """Responde preguntas puntuales del viajero sobre seguridad,
        estafas comunes o costumbres locales de un destino ya confirmado.
        Usar esta tool cuando el usuario pregunta si un lugar es seguro,
        que estafas evitar, cuanto dejar de propina, o cosas similares de
        seguridad/costumbres, no para recomendaciones de actividades o
        comercios."""
        respuestas = responder_faq_viajero(conexion, rotador, destino, consulta, k)
        return [respuesta.model_dump() for respuesta in respuestas]

    return _tool
