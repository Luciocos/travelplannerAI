"""Orquestador del asistente de viajes (RF11, RF12, Fase 5).

RF12: el orquestador decide sola, en cada turno, cual de las tools
nucleo llamar -- el usuario nunca indica un modo. La decision sale de
`_decidir_accion`, que usa el LLM con salida estructurada sobre el
mensaje y el estado actual (mismo patron que `completar_slots`).

Unica excepcion (tambien RF12): `info_destino` no participa de esa
decision. Se dispara sola, una vez por sesion, la primera vez que el
destino queda confirmado (ver `_disparar_info_destino_si_corresponde`).

RF11: `SesionAgente` es la memoria de la conversacion (el estado del
viaje y si ya se disparo info_destino), vive en memoria del proceso
mientras dura la sesion, no se persiste entre sesiones.

El orquestador tambien elige los parametros de refinamiento de la tool
elegida (hoy, `cantidad_resultados`), no solo la tool (D-10 en
DECISIONES.md). Los parametros que ya son estado validado (destino,
fechas, intereses, cantidad de personas) nunca se le piden al LLM: se
inyectan siempre desde `sesion.estado`, la misma fuente de verdad que
mantiene el merge no destructivo de RF2. Pedirselos de nuevo al LLM no
suma nada (el dato ya esta, garantizado por codigo) y sí puede perder
algo (que el LLM transcriba mal o no vea el estado completo).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from asistente_viajes.destinos import buscar_destino_piloto
from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.prompts import PROMPT_DECIDIR_ACCION
from asistente_viajes.tools.armar_plan import PlanDeViaje, armar_plan, guardar_itinerario
from asistente_viajes.tools.completar_slots import completar_slots
from asistente_viajes.tools.info_destino import InfoDestino, info_destino
from asistente_viajes.tools.recomendar_actividades import (
    ActividadRecomendada,
    recomendar_actividades,
)
from asistente_viajes.tools.recomendar_locales import LocalRecomendado, recomendar_locales
from asistente_viajes.tools.responder_faq_viajero import RespuestaFaq, responder_faq_viajero

logger = logging.getLogger(__name__)

Accion = Literal[
    "completar_slots",
    "armar_plan",
    "recomendar_actividades",
    "recomendar_locales",
    "responder_faq_viajero",
]

CANTIDAD_RESULTADOS_DEFECTO = 3


class DecisionAccion(BaseModel):
    accion: Accion
    cantidad_resultados: int | None = Field(
        default=None,
        description=(
            "Cantidad de resultados que el usuario pidio explicitamente "
            "(ej. 'dame 5 opciones', 'solo una'). None si no la menciono."
        ),
    )


@dataclass
class SesionAgente:
    """Memoria de la sesion (RF11)."""

    estado: PreferenciasViaje = field(default_factory=PreferenciasViaje)
    info_destino_disparada: bool = False


def _decidir_accion(rotador: RotadorClavesGemini, mensaje: str, estado: PreferenciasViaje) -> DecisionAccion:
    """RF12: la decision de que tool usar, y con que parametros de
    refinamiento, es siempre del orquestador, nunca del usuario. Los
    parametros que ya son estado validado (destino, fechas, intereses)
    no se le piden aca al LLM, se inyectan directo desde sesion.estado
    en procesar_mensaje (ver D-10)."""
    modelo_estructurado = rotador.con_salida_estructurada(DecisionAccion)
    prompt = PROMPT_DECIDIR_ACCION.format(
        estado_actual=estado.model_dump(),
        slots_faltantes=estado.slots_faltantes(),
        mensaje=mensaje,
    )
    return modelo_estructurado.invoke(prompt)


def _coordenadas_destino(destino: str) -> dict | None:
    """Destinos piloto -> pais/lat/lon, para poder disparar info_destino
    sin pedirle coordenadas al usuario. None si el destino no esta en la
    tabla de referencia (todavia no soportado como piloto). Insensible a
    tildes y mayusculas (ver destinos.py)."""
    encontrado = buscar_destino_piloto(destino)
    return encontrado[1] if encontrado else None


def _disparar_info_destino_si_corresponde(sesion: SesionAgente) -> InfoDestino | None:
    """RF12, unica excepcion: info_destino se dispara sola la primera vez
    que el destino y las fechas quedan confirmados en la sesion, no
    espera que el usuario la pida."""
    estado = sesion.estado
    if sesion.info_destino_disparada:
        return None
    if not (estado.destino and estado.fecha_inicio and estado.fecha_fin):
        return None

    coordenadas = _coordenadas_destino(estado.destino)
    if coordenadas is None:
        logger.warning("destino '%s' sin coordenadas de referencia, no se dispara info_destino", estado.destino)
        return None

    sesion.info_destino_disparada = True
    return info_destino(
        destino=estado.destino,
        pais=coordenadas["pais"],
        lat=coordenadas["lat"],
        lon=coordenadas["lon"],
        fecha_inicio=estado.fecha_inicio,
        fecha_fin=estado.fecha_fin,
    )


def _resumen_plan(plan: PlanDeViaje) -> str:
    lineas = [f"Armé un plan de {len(plan.dias)} día(s) para **{plan.destino}**:"]
    for dia in plan.dias:
        nombres = ", ".join(a.nombre or "actividad sin nombre" for a in dia.actividades)
        lineas.append(f"- **Día {dia.dia}**: {nombres} (costo estimado ${dia.costo_dia:.0f})")
    lineas.append(
        f"\nCosto total estimado: ${plan.costo_total_estimado:.0f} por persona, "
        f"${plan.costo_total_grupo:.0f} para el grupo de {plan.cantidad_personas}."
    )
    return "\n".join(lineas)


def _resumen_actividades(actividades: list[ActividadRecomendada]) -> str:
    if not actividades:
        return "No encontré actividades para recomendarte con esos intereses en este destino."
    lineas = [f"- **{a.nombre}**: {a.justificacion}" for a in actividades]
    return "\n".join(lineas)


def _resumen_locales(locales: list[LocalRecomendado]) -> str:
    if not locales:
        return "No encontré locales para recomendarte con esa consulta en este destino."
    lineas = [f"- **{local.nombre}**: {local.justificacion}" for local in locales]
    return "\n".join(lineas)


def _resumen_faq(respuestas: list[RespuestaFaq]) -> str:
    if not respuestas:
        return "No tengo información sobre seguridad, estafas o costumbres para esa consulta en este destino."
    lineas = [f"- **{r.tema}**: {r.respuesta}" for r in respuestas]
    return "\n".join(lineas)


def procesar_mensaje(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    sesion: SesionAgente,
    mensaje: str,
) -> str:
    """Punto de entrada del orquestador: actualiza la memoria de sesion
    (RF11) segun la accion que decida (RF12) y devuelve la respuesta en
    texto. Dispara info_destino aparte si corresponde."""
    decision = _decidir_accion(rotador, mensaje, sesion.estado)
    accion = decision.accion
    k = decision.cantidad_resultados or CANTIDAD_RESULTADOS_DEFECTO
    logger.info("orquestador elige: %s (cantidad_resultados=%s)", accion, k)

    if accion == "completar_slots":
        sesion.estado, pregunta = completar_slots(rotador, mensaje, sesion.estado)
        respuesta = pregunta or "Ya tengo todo lo que necesito para armar tu viaje."
    elif accion == "armar_plan":
        plan = armar_plan(conexion, sesion.estado)
        guardar_itinerario(conexion, sesion.estado, plan)
        respuesta = _resumen_plan(plan)
    elif accion == "recomendar_actividades":
        actividades = recomendar_actividades(
            conexion, rotador, sesion.estado.destino, sesion.estado.intereses or [], k=k
        )
        respuesta = _resumen_actividades(actividades)
    elif accion == "recomendar_locales":
        locales = recomendar_locales(conexion, rotador, sesion.estado.destino, mensaje, k=k)
        respuesta = _resumen_locales(locales)
    else:  # responder_faq_viajero
        respuestas_faq = responder_faq_viajero(conexion, rotador, sesion.estado.destino, mensaje, k=k)
        respuesta = _resumen_faq(respuestas_faq)

    info = _disparar_info_destino_si_corresponde(sesion)
    if info is not None:
        respuesta = f"{respuesta}\n\n{info.clima.detalle} Idioma: {info.idioma_moneda.idioma}, moneda: {info.idioma_moneda.moneda}."

    return respuesta
