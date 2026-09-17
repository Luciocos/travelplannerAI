"""Capa fina entre la UI (chat_app.py) y la logica de negocio
(asistente_viajes.agente/conversaciones).

Existe por testeabilidad: streamlit.testing.v1.AppTest reejecuta
chat_app.py como modulo nuevo en cada .run(), asi que parchear algo que
chat_app.py importo directo de asistente_viajes.* no tiene efecto en la
proxima corrida. Parchear las funciones de ESTE modulo si funciona,
porque chat_app.py llama a traves de el en cada rerun."""

from __future__ import annotations

import psycopg

from asistente_viajes.agente import SesionAgente, procesar_mensaje
from asistente_viajes.conversaciones import (
    ResumenConversacion,
    cargar_conversacion,
    crear_conversacion,
    eliminar_conversacion,
    guardar_turno,
    listar_conversaciones,
    renombrar_conversacion,
)
from asistente_viajes.llm import RotadorClavesGemini
from asistente_viajes.tools.armar_plan import PlanDeViaje, resumen_markdown


def nueva_conversacion(conexion: psycopg.Connection) -> str:
    return crear_conversacion(conexion)


def listar_chats(conexion: psycopg.Connection) -> list[ResumenConversacion]:
    return listar_conversaciones(conexion)


def cargar_chat(conexion: psycopg.Connection, conversacion_id: str) -> SesionAgente:
    """Nunca None: si el id no existe (por ejemplo, un link viejo a un
    chat borrado), se cae a una sesion nueva en vez de romper la UI."""
    sesion = cargar_conversacion(conexion, conversacion_id)
    return sesion if sesion is not None else SesionAgente()


def responder(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    conversacion_id: str,
    sesion: SesionAgente,
    mensaje: str,
) -> str:
    respuesta = procesar_mensaje(conexion, rotador, sesion, mensaje)
    guardar_turno(conexion, conversacion_id, sesion, mensaje, respuesta)
    return respuesta


def renombrar_chat(conexion: psycopg.Connection, conversacion_id: str, titulo: str) -> None:
    renombrar_conversacion(conexion, conversacion_id, titulo)


def eliminar_chat(conexion: psycopg.Connection, conversacion_id: str) -> None:
    eliminar_conversacion(conexion, conversacion_id)


def itinerario_descargable(sesion: SesionAgente) -> str | None:
    """Markdown del ultimo plan armado en esta sesion, para el boton de
    descarga. None si todavia no se armo ningun plan."""
    if sesion.ultimo_plan is None:
        return None
    return resumen_markdown(PlanDeViaje(**sesion.ultimo_plan))
