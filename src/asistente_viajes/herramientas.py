"""Catalogo de tools que el agente puede llamar (D-25, Fase 7E).

Hasta acá el orquestador decidía con `if`s de precondición en Python y
llamaba las funciones directo, esquivando las `@tool` que el proyecto ya
tenía construidas. Este módulo cierra esa brecha: arma la lista de tools
de LangChain con la conexión y el rotador ya inyectados, para que el modelo
las vea y decida solo cuáles usar (RF12, de verdad esta vez).

Cada tool devuelve un dict con dos claves, que es el mismo contrato de dos
caras que usa `Fragmento` en grafo.py:

- `datos`: los hechos en texto plano. Es lo que vuelve al modelo como
  ToolMessage y lo que después alimenta la redacción.
- `tarjeta`: el HTML ya armado en Python con datos reales, o "" si esta
  acción no tiene nada que tabular.

Esa separación es la que permite que el modelo tenga libertad para decidir
y redactar sin poder inventar un precio ni un lugar: los números se
calculan acá y él solo los cuenta.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import psycopg
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.llm import RotadorClavesGemini

logger = logging.getLogger(__name__)


class ArgsSinParametros(BaseModel):
    """Para las tools que trabajan sobre el estado del viaje ya cargado."""


class ArgsConsulta(BaseModel):
    consulta: str = Field(description="La pregunta puntual del cliente, con sus palabras")


class ArgsCantidad(BaseModel):
    cantidad: int = Field(default=3, description="Cuántos resultados devolver")


class ArgsMoneda(BaseModel):
    moneda: str = Field(default="ARS", description="Código ISO de la moneda, por ejemplo ARS o EUR")


def _tool(
    nombre: str, descripcion: str, esquema: type[BaseModel], funcion: Callable[..., dict]
) -> StructuredTool:
    return StructuredTool.from_function(
        func=funcion, name=nombre, description=descripcion, args_schema=esquema
    )


def construir_herramientas(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    estado: PreferenciasViaje,
    hoy: date,
    ultimo_plan: dict | None,
) -> tuple[list[StructuredTool], dict[str, Any]]:
    """Arma el catalogo para ESTE turno y un acumulador donde las tools
    dejan lo que produjeron.

    El estado del viaje se captura por closure en vez de pedirselo al
    modelo como argumento: son datos que el sistema ya tiene, y hacer que
    el LLM los repita en cada llamada es una invitacion a que los altere.
    El acumulador guarda las tarjetas y el plan nuevo, porque el
    ToolMessage solo puede devolverle texto al modelo.
    """
    # Import local: estas tools arrastran el modelo de embeddings y los
    # clientes HTTP, y no queremos pagarlo al importar el modulo.
    from asistente_viajes.grafo import (
        _datos_alojamiento,
        _datos_plan,
        _datos_recomendaciones,
        _datos_vuelos,
        _resumen_actividades,
        _resumen_alojamiento,
        _resumen_locales,
        _resumen_plan,
        _resumen_vuelos,
    )
    from asistente_viajes.services.cambio import convertir_desde_usd
    from asistente_viajes.services.rapidapi.booking import buscar_alojamiento, buscar_vuelos
    from asistente_viajes.tools.armar_plan import armar_plan, guardar_itinerario
    from asistente_viajes.tools.recomendar_actividades import recomendar_actividades
    from asistente_viajes.tools.recomendar_locales import recomendar_locales
    from asistente_viajes.tools.responder_faq_viajero import responder_faq_viajero

    acumulador: dict[str, Any] = {"fragmentos": [], "ultimo_plan": ultimo_plan}

    def _registrar(tipo: str, datos: str, tarjeta: str = "") -> dict:
        acumulador["fragmentos"].append({"tipo": tipo, "texto": tarjeta, "datos": datos})
        return {"datos": datos}

    def _armar_plan() -> dict:
        plan = armar_plan(conexion, estado)
        guardar_itinerario(conexion, estado, plan)
        acumulador["ultimo_plan"] = plan.model_dump(mode="json")
        return _registrar("armar_plan", _datos_plan(plan), _resumen_plan(plan))

    def _recomendar_actividades(cantidad: int = 3) -> dict:
        actividades = recomendar_actividades(
            conexion, rotador, estado.destino, estado.intereses or [], k=cantidad
        )
        return _registrar(
            "recomendar_actividades",
            _datos_recomendaciones("actividades", actividades),
            _resumen_actividades(actividades),
        )

    def _recomendar_locales(consulta: str) -> dict:
        locales = recomendar_locales(conexion, rotador, estado.destino, consulta, k=3)
        return _registrar(
            "recomendar_locales",
            _datos_recomendaciones("locales", locales),
            _resumen_locales(locales),
        )

    def _responder_faq(consulta: str) -> dict:
        respuesta = responder_faq_viajero(conexion, rotador, estado.destino, consulta, k=3)
        return _registrar("responder_faq_viajero", respuesta.respuesta)

    def _buscar_alojamiento() -> dict:
        habitaciones = -(-(estado.cantidad_personas or 1) // 2)
        alojamientos = buscar_alojamiento(
            conexion,
            estado.destino,
            estado.fecha_inicio,
            estado.fecha_fin,
            adultos=estado.cantidad_personas or 1,
            habitaciones=habitaciones,
        )
        return _registrar(
            "buscar_alojamiento",
            _datos_alojamiento(alojamientos),
            _resumen_alojamiento(alojamientos),
        )

    def _buscar_vuelos() -> dict:
        vuelos = buscar_vuelos(
            conexion,
            estado.origen,
            estado.destino,
            estado.fecha_inicio,
            estado.fecha_fin,
            adultos=estado.cantidad_personas or 1,
        )
        return _registrar("buscar_vuelos", _datos_vuelos(vuelos), _resumen_vuelos(vuelos))

    def _convertir_moneda(moneda: str = "ARS") -> dict:
        plan = acumulador["ultimo_plan"] or {}
        monto = plan.get("costo_total_grupo") or 0.0
        if not monto:
            return _registrar(
                "convertir_moneda",
                "Todavia no hay un plan armado con un costo para convertir.",
            )
        return _registrar("convertir_moneda", convertir_desde_usd(monto, moneda).detalle)

    herramientas = [
        _tool(
            "armar_plan",
            "Arma el itinerario dia a dia del viaje, con actividades reales agrupadas por "
            "cercania y el costo estimado. Usala cuando el cliente pida el plan o el "
            "itinerario, y TAMBIEN cada vez que pida cambiarlo (dejar un dia libre, sacar "
            "un tipo de lugar, cambiar el ritmo): el plan se re-arma con los ajustes ya "
            "cargados en el estado. Requiere destino y fechas o cantidad de dias.",
            ArgsSinParametros,
            _armar_plan,
        ),
        _tool(
            "recomendar_actividades",
            "Recomienda actividades y lugares para visitar en el destino, segun los "
            "intereses del cliente. Usala cuando pida sugerencias sueltas o quiera MAS "
            "opciones que las que ya tiene, sin pedir el itinerario completo.",
            ArgsCantidad,
            _recomendar_actividades,
        ),
        _tool(
            "recomendar_locales",
            "Responde donde comer, tomar algo o comprar en el destino. Pasale como "
            "consulta solo el fragmento del mensaje que corresponde a ese pedido.",
            ArgsConsulta,
            _recomendar_locales,
        ),
        _tool(
            "responder_faq_viajero",
            "Responde consultas sobre seguridad, estafas comunes y costumbres locales del "
            "destino. No sirve para actividades ni para comercios.",
            ArgsConsulta,
            _responder_faq,
        ),
        _tool(
            "buscar_alojamiento",
            "Busca hoteles reales en el destino. Requiere fechas exactas de ida y vuelta.",
            ArgsSinParametros,
            _buscar_alojamiento,
        ),
        _tool(
            "buscar_vuelos",
            "Busca vuelos reales hacia el destino. Requiere fechas exactas y la ciudad de "
            "origen del cliente.",
            ArgsSinParametros,
            _buscar_vuelos,
        ),
        _tool(
            "convertir_moneda",
            "Convierte el costo total del ultimo plan armado a otra moneda, con cotizacion "
            "real. Usala cuando pregunten cuanto sale en pesos, euros u otra moneda.",
            ArgsMoneda,
            _convertir_moneda,
        ),
    ]
    return herramientas, acumulador
