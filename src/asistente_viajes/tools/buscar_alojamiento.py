"""Tool de LangChain: buscar_alojamiento (RF6, extension).

Sobre services/rapidapi/booking.py. Booking.com15 es la unica fuente real
(Fly Scraper no tiene endpoints de busqueda funcionando, ver
migracion-amadeus-a-rapidapi.md). Si la API falla, la tool devuelve datos
de fixture explicitamente marcados (`es_fixture=True`) para que el LLM
nunca los presente como precios reales.
"""

from __future__ import annotations

from datetime import date

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.services.rapidapi.booking import buscar_alojamiento as _buscar_alojamiento


class ArgsBuscarAlojamiento(BaseModel):
    destino: str = Field(description="Destino confirmado del viaje, por ejemplo 'Barcelona'")
    fecha_inicio: date = Field(description="Fecha de check-in, ISO YYYY-MM-DD")
    fecha_fin: date = Field(description="Fecha de check-out, ISO YYYY-MM-DD")
    adultos: int = Field(default=2, description="Cantidad de adultos")
    habitaciones: int = Field(default=1, description="Cantidad de habitaciones")


def crear_tool_buscar_alojamiento(conexion: psycopg.Connection):
    """Arma la tool de LangChain con la conexion ya inyectada (se resuelve
    una vez al armar el agente, no en cada llamada)."""

    @tool("buscar_alojamiento", args_schema=ArgsBuscarAlojamiento)
    def _tool(
        destino: str, fecha_inicio: date, fecha_fin: date, adultos: int = 2, habitaciones: int = 1
    ) -> list[dict]:
        """Busca opciones de alojamiento (hoteles) en un destino ya
        confirmado, para un rango de fechas. Usar esta tool cuando el
        usuario pida donde alojarse o cuanto sale el hotel, con destino y
        fechas ya conocidos. Si la respuesta incluye `es_fixture: true`,
        son datos de ejemplo, no precios reales: aclarar eso al usuario."""
        resultados = _buscar_alojamiento(
            conexion, destino, fecha_inicio, fecha_fin, adultos=adultos, habitaciones=habitaciones
        )
        return [alojamiento.model_dump() for alojamiento in resultados]

    return _tool
