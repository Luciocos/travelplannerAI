"""Persistencia de chats (RF11 extendido, Fase 7C, D-13).

Antes SesionAgente vivia solo en memoria del proceso: refrescar la
pagina o cerrar el navegador perdia toda la conversacion, un bug real
encontrado probando la app. Este modulo guarda y recupera conversaciones
completas contra Postgres (sql/002_conversaciones.sql).

`mensaje` es la fuente de verdad del historial; `conversacion.sesion`
guarda solo el estado derivado (PreferenciasViaje, el ultimo plan armado,
que destino ya mostro info_destino), nunca el historial de texto, para
no tener dos copias que puedan desincronizarse.

Sigue la misma convencion que el resto de src/ (ver armar_plan.guardar_itinerario):
no hace commit() por si solo, el caller lo hace vía `with obtener_conexion()`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime

import psycopg

from asistente_viajes.agente import SesionAgente
from asistente_viajes.estado import PreferenciasViaje

logger = logging.getLogger(__name__)

ESQUEMA_VERSION_ACTUAL = 1
MENSAJES_A_CARGAR = 20


@dataclass
class ResumenConversacion:
    id: str
    titulo: str
    actualizada_en: datetime


def crear_conversacion(conexion: psycopg.Connection) -> str:
    with conexion.cursor() as cursor:
        cursor.execute("INSERT INTO conversacion DEFAULT VALUES RETURNING id;")
        (id_,) = cursor.fetchone()
    return str(id_)


def listar_conversaciones(conexion: psycopg.Connection) -> list[ResumenConversacion]:
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT id, titulo, actualizada_en FROM conversacion ORDER BY actualizada_en DESC;"
        )
        filas = cursor.fetchall()
    return [
        ResumenConversacion(id=str(id_), titulo=titulo, actualizada_en=actualizada_en)
        for id_, titulo, actualizada_en in filas
    ]


def _sesion_desde_jsonb(datos: dict) -> SesionAgente:
    estado = PreferenciasViaje(**(datos.get("estado") or {}))
    return SesionAgente(
        estado=estado,
        ultimo_plan=datos.get("ultimo_plan"),
        info_destino_mostrada_para=datos.get("info_destino_mostrada_para"),
    )


def cargar_conversacion(conexion: psycopg.Connection, conversacion_id: str) -> SesionAgente | None:
    """None si la conversacion no existe. Si el esquema de `sesion`
    quedo obsoleto o no se puede reconstruir, degrada a estado vacio en
    vez de romper (D-13): un chat viejo se puede seguir usando, solo
    perdio el estado derivado, no el historial (eso se recarga siempre
    desde `mensaje`, la fuente de verdad)."""
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT sesion, esquema_version FROM conversacion WHERE id = %s;", (conversacion_id,)
        )
        fila = cursor.fetchone()
        if fila is None:
            return None
        sesion_jsonb, esquema_version = fila

        cursor.execute(
            "SELECT rol, texto FROM mensaje WHERE conversacion_id = %s ORDER BY orden DESC LIMIT %s;",
            (conversacion_id, MENSAJES_A_CARGAR),
        )
        mensajes = list(reversed(cursor.fetchall()))

    if esquema_version != ESQUEMA_VERSION_ACTUAL:
        logger.warning(
            "conversacion %s con esquema_version %s (actual %s), se degrada a estado vacio",
            conversacion_id,
            esquema_version,
            ESQUEMA_VERSION_ACTUAL,
        )
        sesion = SesionAgente()
    else:
        try:
            sesion = _sesion_desde_jsonb(sesion_jsonb)
        except Exception:
            logger.exception(
                "no se pudo reconstruir la sesion de %s, se degrada a estado vacio", conversacion_id
            )
            sesion = SesionAgente()

    sesion.historial = [{"rol": rol, "texto": texto} for rol, texto in mensajes]
    return sesion


def _titulo_automatico(sesion: SesionAgente) -> str | None:
    """None si todavia no hay destino: se deja el titulo por defecto
    hasta que haya algo mas concreto para mostrar en la lista de chats."""
    estado = sesion.estado
    if not estado.destino:
        return None
    if estado.fecha_inicio and estado.fecha_fin:
        rango = f"{estado.fecha_inicio.strftime('%d/%m')}-{estado.fecha_fin.strftime('%d/%m')}"
        return f"{estado.destino} · {rango}"
    return estado.destino


def guardar_turno(
    conexion: psycopg.Connection,
    conversacion_id: str,
    sesion: SesionAgente,
    mensaje_usuario: str,
    respuesta: str,
) -> None:
    """Persiste un turno completo (los 2 mensajes de texto y el estado
    derivado actualizado) en una sola conexion. El titulo automatico
    nunca pisa un titulo puesto a mano (titulo_manual)."""
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(MAX(orden), 0) FROM mensaje WHERE conversacion_id = %s;",
            (conversacion_id,),
        )
        (orden_actual,) = cursor.fetchone()

        cursor.execute(
            """
            INSERT INTO mensaje (conversacion_id, orden, rol, texto)
            VALUES (%s, %s, 'usuario', %s), (%s, %s, 'asistente', %s);
            """,
            (
                conversacion_id,
                orden_actual + 1,
                mensaje_usuario,
                conversacion_id,
                orden_actual + 2,
                respuesta,
            ),
        )

        sesion_jsonb = json.dumps(
            {
                "estado": sesion.estado.model_dump(mode="json"),
                "ultimo_plan": sesion.ultimo_plan,
                "info_destino_mostrada_para": sesion.info_destino_mostrada_para,
            }
        )
        titulo_automatico = _titulo_automatico(sesion)
        cursor.execute(
            """
            UPDATE conversacion
            SET sesion = %s,
                esquema_version = %s,
                actualizada_en = now(),
                titulo = CASE WHEN titulo_manual THEN titulo ELSE COALESCE(%s, titulo) END
            WHERE id = %s;
            """,
            (sesion_jsonb, ESQUEMA_VERSION_ACTUAL, titulo_automatico, conversacion_id),
        )


def renombrar_conversacion(conexion: psycopg.Connection, conversacion_id: str, titulo: str) -> None:
    with conexion.cursor() as cursor:
        cursor.execute(
            "UPDATE conversacion SET titulo = %s, titulo_manual = true WHERE id = %s;",
            (titulo, conversacion_id),
        )


def eliminar_conversacion(conexion: psycopg.Connection, conversacion_id: str) -> None:
    with conexion.cursor() as cursor:
        cursor.execute("DELETE FROM conversacion WHERE id = %s;", (conversacion_id,))
