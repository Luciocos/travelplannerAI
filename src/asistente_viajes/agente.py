"""Fachada del orquestador (RF11, Fase 7C).

La logica del orquestador vive en grafo.py (D-12): este modulo solo
mantiene `SesionAgente` (la memoria de la conversacion, RF11) y traduce
entre esa memoria y el grafo turno a turno. Es el punto que usan la UI,
el CLI (scripts/chat.py) y el notebook, para no acoplar a ninguno de
ellos con el estado interno del grafo (mensaje, interpretacion,
pendientes, fragmentos) que solo le importa a grafo.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import psycopg

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.grafo import procesar_turno
from asistente_viajes.llm import RotadorClavesGemini

TURNOS_DE_HISTORIAL_GUARDADOS = 20


@dataclass
class SesionAgente:
    """Memoria de la sesion (RF11): estado del viaje, historial de texto
    (para que el LLM pueda responder preguntas de recap, "gracias", etc.
    sin necesitar mas contexto que este), el ultimo plan armado (para
    "¿cual es la mas barata?" y para re-armarlo si algo cambia) y el
    destino para el que ya se mostro info_destino."""

    estado: PreferenciasViaje = field(default_factory=PreferenciasViaje)
    historial: list[dict] = field(default_factory=list)
    ultimo_plan: dict | None = None
    info_destino_mostrada_para: str | None = None


def procesar_mensaje(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    sesion: SesionAgente,
    mensaje: str,
    hoy: date | None = None,
) -> str:
    """Punto de entrada del orquestador: corre un turno del grafo,
    actualiza la memoria de la sesion con el resultado, y devuelve la
    respuesta en texto."""
    resultado = procesar_turno(
        conexion=conexion,
        rotador=rotador,
        mensaje=mensaje,
        historial=sesion.historial,
        estado=sesion.estado.model_dump(mode="json"),
        ultimo_plan=sesion.ultimo_plan,
        info_destino_mostrada_para=sesion.info_destino_mostrada_para,
        hoy=hoy,
    )

    sesion.estado = PreferenciasViaje(**resultado["estado"])
    sesion.ultimo_plan = resultado["ultimo_plan"]
    sesion.info_destino_mostrada_para = resultado["info_destino_mostrada_para"]

    respuesta_texto = resultado["respuesta_texto"]
    sesion.historial.append({"rol": "usuario", "texto": mensaje})
    sesion.historial.append({"rol": "asistente", "texto": respuesta_texto})
    sesion.historial = sesion.historial[-TURNOS_DE_HISTORIAL_GUARDADOS:]

    return respuesta_texto
