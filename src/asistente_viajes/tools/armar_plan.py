"""Tool de LangChain: armar_plan (RF5, nucleo, Fase 6).

Itinerario dia a dia con 2 o 3 actividades reales por dia y costo
estimado. El LLM no participa en esta tool: el costo sale de una tabla
fija de costo base por categoria (ver COSTO_BASE_POR_CATEGORIA), nunca de
un numero generado por el modelo. Es logica de negocio determinista sobre
lo que ya recupero el RAG, no generacion (util para la defensa: no todo
el sistema es RAG+LLM).

Persiste en `itinerario` e `itinerario_item` (sql/001_schema.sql).
"""

from __future__ import annotations

from datetime import date

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.recuperacion.atractivos import buscar_atractivos

ACTIVIDADES_POR_DIA_MIN = 2
ACTIVIDADES_POR_DIA_MAX = 3

# Costo estimado en USD por categoria de OpenTripMap (primer valor de la
# lista separada por comas). Aproximado y documentado a proposito: no es
# un dato recuperado del corpus ni generado por el LLM, es una tabla fija
# que se puede ajustar y explicar en la defensa.
COSTO_BASE_POR_CATEGORIA: dict[str, float] = {
    "museums": 10.0,
    "historic": 5.0,
    "architecture": 0.0,
    "natural": 5.0,
    "cultural": 5.0,
}
COSTO_BASE_DEFAULT = 5.0

SQL_INSERTAR_ITINERARIO = """
INSERT INTO itinerario (destino, fecha_inicio, fecha_fin, cantidad_personas, presupuesto, costo_estimado)
VALUES (%(destino)s, %(fecha_inicio)s, %(fecha_fin)s, %(cantidad_personas)s, %(presupuesto)s, %(costo_estimado)s)
RETURNING id;
"""

SQL_INSERTAR_ITEM = """
INSERT INTO itinerario_item (itinerario_id, dia, orden, descripcion, costo_estimado)
VALUES (%(itinerario_id)s, %(dia)s, %(orden)s, %(descripcion)s, %(costo_estimado)s);
"""


class ActividadDelPlan(BaseModel):
    nombre: str | None
    categoria: str | None
    costo_estimado: float


class DiaDelPlan(BaseModel):
    dia: int
    actividades: list[ActividadDelPlan]
    costo_dia: float


class PlanDeViaje(BaseModel):
    destino: str
    dias: list[DiaDelPlan]
    costo_total_estimado: float
    cantidad_personas: int
    costo_total_grupo: float


class ArgsArmarPlan(BaseModel):
    estado: PreferenciasViaje = Field(
        description="Preferencias del viaje ya completas: destino, fechas y cantidad de personas"
    )


def _costo_actividad(categoria: str | None) -> float:
    if not categoria:
        return COSTO_BASE_DEFAULT
    primera_categoria = categoria.split(",")[0].strip()
    return COSTO_BASE_POR_CATEGORIA.get(primera_categoria, COSTO_BASE_DEFAULT)


def _cantidad_dias(fecha_inicio: date, fecha_fin: date) -> int:
    return max((fecha_fin - fecha_inicio).days + 1, 1)


def _repartir_por_dia(candidatos: list[ResultadoRecuperado], dias_totales: int) -> list[DiaDelPlan]:
    """2 o 3 actividades reales por dia, sin repetir, en el orden en que
    vinieron recuperadas (ya ordenadas por similitud semantica)."""
    dias: list[DiaDelPlan] = []
    indice = 0
    for numero_dia in range(1, dias_totales + 1):
        restantes_para_dias_futuros = (dias_totales - numero_dia) * ACTIVIDADES_POR_DIA_MIN
        cantidad_hoy = ACTIVIDADES_POR_DIA_MAX
        if len(candidatos) - indice - cantidad_hoy < restantes_para_dias_futuros:
            cantidad_hoy = ACTIVIDADES_POR_DIA_MIN

        actividades_dia = []
        for _ in range(cantidad_hoy):
            if indice >= len(candidatos):
                break
            resultado = candidatos[indice]
            indice += 1
            actividades_dia.append(
                ActividadDelPlan(
                    nombre=resultado.nombre,
                    categoria=resultado.categoria,
                    costo_estimado=_costo_actividad(resultado.categoria),
                )
            )
        costo_dia = sum(actividad.costo_estimado for actividad in actividades_dia)
        dias.append(DiaDelPlan(dia=numero_dia, actividades=actividades_dia, costo_dia=costo_dia))
    return dias


def armar_plan(conexion: psycopg.Connection, estado: PreferenciasViaje) -> PlanDeViaje:
    """Logica pura de la tool, sin el decorador. Asume que `estado` ya
    tiene destino, fechas y cantidad_personas (RF11 se encarga de eso
    antes de llegar aca, no se valida de nuevo)."""
    dias_totales = _cantidad_dias(estado.fecha_inicio, estado.fecha_fin)
    intereses = estado.intereses or []
    candidatos = buscar_atractivos(
        conexion, destino=estado.destino, intereses=intereses, k=dias_totales * ACTIVIDADES_POR_DIA_MAX
    )

    dias = _repartir_por_dia(candidatos, dias_totales)
    costo_total = sum(dia.costo_dia for dia in dias)
    cantidad_personas = estado.cantidad_personas or 1

    return PlanDeViaje(
        destino=estado.destino,
        dias=dias,
        costo_total_estimado=costo_total,
        cantidad_personas=cantidad_personas,
        costo_total_grupo=costo_total * cantidad_personas,
    )


def guardar_itinerario(conexion: psycopg.Connection, estado: PreferenciasViaje, plan: PlanDeViaje) -> int:
    """Persiste el plan en itinerario/itinerario_item. Devuelve el id del
    itinerario creado."""
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_INSERTAR_ITINERARIO,
            {
                "destino": estado.destino,
                "fecha_inicio": estado.fecha_inicio,
                "fecha_fin": estado.fecha_fin,
                "cantidad_personas": plan.cantidad_personas,
                "presupuesto": estado.presupuesto,
                "costo_estimado": plan.costo_total_estimado,
            },
        )
        (itinerario_id,) = cursor.fetchone()

        for dia in plan.dias:
            for orden, actividad in enumerate(dia.actividades, start=1):
                cursor.execute(
                    SQL_INSERTAR_ITEM,
                    {
                        "itinerario_id": itinerario_id,
                        "dia": dia.dia,
                        "orden": orden,
                        "descripcion": actividad.nombre or "Actividad sin nombre",
                        "costo_estimado": actividad.costo_estimado,
                    },
                )
    return itinerario_id


def crear_tool_armar_plan(conexion: psycopg.Connection):
    """Arma la tool de LangChain, con la conexion ya inyectada."""

    @tool("armar_plan", args_schema=ArgsArmarPlan)
    def _tool(estado: PreferenciasViaje) -> dict:
        """Arma un itinerario dia a dia para un viaje ya completo (destino,
        fechas y cantidad de personas conocidos), con 2 o 3 actividades
        reales por dia y un costo estimado total. Usar esta tool cuando el
        usuario pida el plan o itinerario completo del viaje, no para
        consultas puntuales de una sola actividad o recomendacion."""
        plan = armar_plan(conexion, estado)
        guardar_itinerario(conexion, estado, plan)
        return plan.model_dump()

    return _tool
