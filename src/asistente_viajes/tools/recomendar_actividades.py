"""Tool de LangChain: recomendar_actividades (RF3).

Filtra el corpus de atractivos por destino, busca semanticamente por los
intereses declarados, y genera una linea de justificacion por LLM
SOLO a partir del texto recuperado (nunca agrega datos que no esten ahi).
"""

from __future__ import annotations

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.prompts import PROMPT_JUSTIFICAR_RECOMENDACION
from asistente_viajes.recuperacion.atractivos import buscar_atractivos


class ActividadRecomendada(BaseModel):
    nombre: str | None
    categoria: str | None
    justificacion: str


class ArgsRecomendarActividades(BaseModel):
    destino: str = Field(description="Destino confirmado del viaje")
    intereses: list[str] = Field(description="Intereses declarados por el usuario")
    k: int = Field(default=5, description="Cantidad maxima de actividades a recomendar")


def _justificar(rotador: RotadorClavesGemini, texto: str, intereses: list[str]) -> str:
    prompt = PROMPT_JUSTIFICAR_RECOMENDACION.format(
        intereses_o_consulta=", ".join(intereses), texto_recuperado=texto
    )
    respuesta = rotador.invocar(prompt)
    return getattr(respuesta, "content", str(respuesta)).strip()


def recomendar_actividades(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    destino: str,
    intereses: list[str],
    k: int = 5,
) -> list[ActividadRecomendada]:
    """Logica pura de la tool, sin el decorador, para poder testearla
    inyectando conexion y rotador falsos. `crear_tool_recomendar_actividades`
    la envuelve para el agente."""
    resultados = buscar_atractivos(conexion, destino=destino, intereses=intereses, k=k)
    return [
        ActividadRecomendada(
            nombre=resultado.nombre,
            categoria=resultado.categoria,
            justificacion=_justificar(rotador, resultado.texto, intereses),
        )
        for resultado in resultados
    ]


def crear_tool_recomendar_actividades(conexion: psycopg.Connection, rotador: RotadorClavesGemini):
    """Arma la tool de LangChain, con la conexion y el rotador ya inyectados
    (se resuelven una vez al armar el agente, no en cada llamada)."""

    @tool("recomendar_actividades", args_schema=ArgsRecomendarActividades)
    def _tool(destino: str, intereses: list[str], k: int = 5) -> list[dict]:
        """Recomienda actividades y atractivos turisticos en un destino ya
        confirmado, segun los intereses declarados por el usuario (por
        ejemplo historia, naturaleza, gastronomia). Usar esta tool cuando el
        usuario pida actividades o que le arme un plan y ya se sepa el
        destino y al menos un interes."""
        actividades = recomendar_actividades(conexion, rotador, destino, intereses, k)
        return [actividad.model_dump() for actividad in actividades]

    return _tool
