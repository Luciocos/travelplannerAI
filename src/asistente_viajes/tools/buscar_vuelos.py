"""Tool de LangChain: buscar_vuelos (RF7, extension).

Sobre services/rapidapi/booking.py. Booking.com15 es la unica fuente real
de busqueda de vuelos (Fly Scraper no tiene endpoints de busqueda
funcionando, ver migracion-amadeus-a-rapidapi.md). Si la API falla, la
tool devuelve datos de fixture explicitamente marcados (`es_fixture=True`)
para que el LLM nunca los presente como precios reales.
"""

from __future__ import annotations

from datetime import date

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.services.rapidapi.booking import buscar_vuelos as _buscar_vuelos


class ArgsBuscarVuelos(BaseModel):
    origen: str = Field(description="Ciudad o aeropuerto de origen, por ejemplo 'Buenos Aires'")
    destino: str = Field(description="Destino confirmado del viaje, por ejemplo 'Cancun'")
    fecha_salida: date = Field(description="Fecha de salida, ISO YYYY-MM-DD")
    fecha_regreso: date | None = Field(
        default=None, description="Fecha de regreso, si es ida y vuelta"
    )
    adultos: int = Field(default=1, description="Cantidad de adultos")


def crear_tool_buscar_vuelos(conexion: psycopg.Connection):
    """Arma la tool de LangChain con la conexion ya inyectada (se resuelve
    una vez al armar el agente, no en cada llamada)."""

    @tool("buscar_vuelos", args_schema=ArgsBuscarVuelos)
    def _tool(
        origen: str,
        destino: str,
        fecha_salida: date,
        fecha_regreso: date | None = None,
        adultos: int = 1,
    ) -> list[dict]:
        """Busca opciones de vuelo entre un origen y un destino ya
        confirmados, para una fecha de salida (y opcionalmente de
        regreso). Usar esta tool cuando el usuario pida vuelos o cuanto
        sale llegar al destino, con origen, destino y fecha ya conocidos.
        Si la respuesta incluye `es_fixture: true`, son datos de ejemplo,
        no precios reales: aclarar eso al usuario."""
        resultados = _buscar_vuelos(
            conexion, origen, destino, fecha_salida, fecha_regreso, adultos=adultos
        )
        return [vuelo.model_dump() for vuelo in resultados]

    return _tool
