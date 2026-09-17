"""Tool: convertir_moneda (extension, D-18).

Convierte un monto en USD (la moneda en la que armar_plan estima costos,
ver costos.py) a otra moneda, con una cotizacion en vivo (services/cambio.py).
No es RAG ni necesita LLM: es una consulta a una fuente externa mas un
calculo determinista, igual criterio que info_destino con el clima.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.services.cambio import Cotizacion, convertir_desde_usd


class ArgsConvertirMoneda(BaseModel):
    monto_usd: float = Field(description="Monto en USD a convertir")
    moneda_destino: str = Field(description="Codigo de moneda destino, por ejemplo 'ARS', 'EUR'")


def convertir_moneda(monto_usd: float, moneda_destino: str) -> Cotizacion:
    return convertir_desde_usd(monto_usd, moneda_destino)


def crear_tool_convertir_moneda():
    """Arma la tool de LangChain. No necesita conexion ni rotador."""

    @tool("convertir_moneda", args_schema=ArgsConvertirMoneda)
    def _tool(monto_usd: float, moneda_destino: str) -> dict:
        """Convierte un monto en USD a otra moneda con una cotizacion en
        vivo. Usar cuando el cliente pregunta cuanto sale algo (por
        ejemplo el costo de un plan ya armado) en otra moneda, sobre todo
        pesos argentinos."""
        return convertir_moneda(monto_usd, moneda_destino).__dict__

    return _tool
