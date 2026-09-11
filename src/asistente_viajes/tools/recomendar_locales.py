"""Tool de LangChain: recomendar_locales (RF4).

Mismo patron que recomendar_actividades pero sobre el corpus de comercios
y gastronomia, devuelve tambien direccion y rango de precio.
"""

from __future__ import annotations

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.llm import RotadorClavesGemini, contenido_texto
from asistente_viajes.prompts import PROMPT_JUSTIFICAR_RECOMENDACION
from asistente_viajes.recuperacion.comercios import buscar_comercios


class LocalRecomendado(BaseModel):
    nombre: str | None
    categoria: str | None
    direccion: str | None
    rango_precio: str | None
    justificacion: str


class ArgsRecomendarLocales(BaseModel):
    destino: str = Field(description="Destino confirmado del viaje")
    consulta: str = Field(
        description="Consulta puntual del usuario, por ejemplo 'donde comer barato'"
    )
    k: int = Field(default=5, description="Cantidad maxima de locales a recomendar")


def _justificar(rotador: RotadorClavesGemini, texto: str, consulta: str) -> str:
    prompt = PROMPT_JUSTIFICAR_RECOMENDACION.format(
        intereses_o_consulta=consulta, texto_recuperado=texto
    )
    respuesta = rotador.invocar(prompt)
    return contenido_texto(respuesta)


def recomendar_locales(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    destino: str,
    consulta: str,
    k: int = 5,
) -> list[LocalRecomendado]:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando conexion y rotador falsos."""
    resultados = buscar_comercios(conexion, destino=destino, consulta=consulta, k=k)
    return [
        LocalRecomendado(
            nombre=resultado.nombre,
            categoria=resultado.categoria,
            direccion=resultado.direccion,
            rango_precio=resultado.rango_precio,
            justificacion=_justificar(rotador, resultado.texto, consulta),
        )
        for resultado in resultados
    ]


def crear_tool_recomendar_locales(conexion: psycopg.Connection, rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con la conexion y el rotador ya inyectados."""

    @tool("recomendar_locales", args_schema=ArgsRecomendarLocales)
    def _tool(destino: str, consulta: str, k: int = 5) -> list[dict]:
        """Responde consultas puntuales de recomendacion local dentro de un
        destino ya confirmado: donde comer, donde comprar algo tipico, ferias
        o locales de una categoria particular. Usar esta tool cuando el
        usuario pregunta algo concreto sobre comercios o gastronomia, no
        cuando pide el plan completo del viaje."""
        locales = recomendar_locales(conexion, rotador, destino, consulta, k)
        return [local.model_dump() for local in locales]

    return _tool
