"""GUI de demo del asistente de viajes (Streamlit, Fase 7B/7C).

Capa de presentacion pura: la logica de negocio vive en
asistente_viajes.agente/conversaciones, a traves de servicio.py (ver ese
modulo para por que existe esa capa intermedia). No es el entregable
oficial (el notebook lo es, ver consigna-catedra.md); se agrego por
pedido explicito del usuario para que la demo se vea mejor que el CLI de
texto plano.

Uso: streamlit run ui/chat_app.py
"""

from __future__ import annotations

import logging

import psycopg
import servicio
import streamlit as st

from asistente_viajes.config import ConfiguracionInvalida
from asistente_viajes.db import obtener_conexion
from asistente_viajes.llm import crear_rotador

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Asistente de viajes", page_icon="🧳")

OPCIONES_PREDEFINIDAS = [
    (
        "Quiero armar un viaje a Cancún, playa, me interesa la historia, presupuesto medio, "
        "del 1 al 5 de diciembre de 2026, somos 2 personas"
    ),
    "¿Qué puedo visitar en Barcelona?",
    "¿Es seguro tomar un taxi en Cancún?",
]


@st.cache_resource
def _rotador():
    return crear_rotador()


def _chat_activo(conexion) -> str:
    """El id de la conversacion activa vive en la URL (st.query_params),
    no solo en session_state: asi refrescar la pagina no pierde el chat
    (antes, SesionAgente vivia solo en memoria del proceso y un refresh
    perdia todo, un bug real reportado probando la app)."""
    id_en_url = st.query_params.get("c")
    if id_en_url:
        return id_en_url
    nuevo_id = servicio.nueva_conversacion(conexion)
    st.query_params["c"] = nuevo_id
    return nuevo_id


def _cambiar_de_chat(conversacion_id: str) -> None:
    st.query_params["c"] = conversacion_id
    for clave in ("sesion", "chat_actual", "renombrando"):
        st.session_state.pop(clave, None)


def _sidebar(conexion, conversacion_id: str) -> None:
    with st.sidebar:
        if st.button("➕ Nueva conversación", width="stretch"):
            _cambiar_de_chat(servicio.nueva_conversacion(conexion))
            st.rerun()

        st.divider()
        st.caption("Sus conversaciones")
        for chat in servicio.listar_chats(conexion):
            es_actual = chat.id == conversacion_id
            columnas = st.columns([5, 1, 1])
            with columnas[0]:
                if st.button(
                    chat.titulo, key=f"abrir_{chat.id}", width="stretch", disabled=es_actual
                ):
                    _cambiar_de_chat(chat.id)
                    st.rerun()
            with columnas[1]:
                if st.button("✏️", key=f"renombrar_{chat.id}", help="Renombrar"):
                    st.session_state["renombrando"] = chat.id
            with columnas[2]:
                if st.button("🗑️", key=f"borrar_{chat.id}", help="Eliminar"):
                    servicio.eliminar_chat(conexion, chat.id)
                    if es_actual:
                        _cambiar_de_chat(servicio.nueva_conversacion(conexion))
                    st.rerun()

            if st.session_state.get("renombrando") == chat.id:
                nuevo_titulo = st.text_input(
                    "Nuevo título", value=chat.titulo, key=f"titulo_{chat.id}"
                )
                col_ok, col_cancelar = st.columns(2)
                if col_ok.button("Guardar", key=f"guardar_titulo_{chat.id}"):
                    servicio.renombrar_chat(conexion, chat.id, nuevo_titulo)
                    del st.session_state["renombrando"]
                    st.rerun()
                if col_cancelar.button("Cancelar", key=f"cancelar_titulo_{chat.id}"):
                    del st.session_state["renombrando"]
                    st.rerun()


def _sugerencias_para_arrancar() -> str | None:
    """Solo para un chat vacio (sin mensajes todavia): se muestra en el
    area central, no en la sidebar, como las sugerencias de arranque de
    cualquier chat (ChatGPT, Claude, etc). Devuelve el texto elegido, o
    None si el usuario todavia no eligio ninguno."""
    st.subheader("Para arrancar")
    st.caption(
        "Estos botones mandan el mismo texto que escribirías a mano: el orquestador sigue decidiendo solo qué hacer (RF12)."
    )
    for opcion in OPCIONES_PREDEFINIDAS:
        if st.button(opcion, width="stretch", key=f"predef_{opcion}"):
            return opcion
    return None


def _responder(conexion, conversacion_id: str, mensaje: str) -> str:
    return servicio.responder(
        conexion, _rotador(), conversacion_id, st.session_state.sesion, mensaje
    )


def main() -> None:
    st.title("🧳 Asistente de viajes")
    st.caption("Destinos piloto: Barcelona, Miami o Cancún. Cuénteme qué viaje está buscando.")

    try:
        _rotador()
    except ConfiguracionInvalida as error:
        st.error(f"Error de configuración: {error}")
        return

    try:
        with obtener_conexion() as conexion:
            conversacion_id = _chat_activo(conexion)

            if st.session_state.get("chat_actual") != conversacion_id:
                st.session_state.sesion = servicio.cargar_chat(conexion, conversacion_id)
                st.session_state.chat_actual = conversacion_id

            _sidebar(conexion, conversacion_id)

            for turno in st.session_state.sesion.historial:
                with st.chat_message("user" if turno["rol"] == "usuario" else "assistant"):
                    st.markdown(turno["texto"])

            mensaje_de_boton = None
            if not st.session_state.sesion.historial:
                mensaje_de_boton = _sugerencias_para_arrancar()

            mensaje_escrito = st.chat_input("Escriba su mensaje...")
            mensaje = mensaje_de_boton or mensaje_escrito

            if mensaje:
                with st.chat_message("user"):
                    st.markdown(mensaje)
                with st.chat_message("assistant"):
                    with st.spinner(
                        "Pensando... (puede tardar, la cuota gratis de Gemini a veces anda lenta)"
                    ):
                        try:
                            respuesta = _responder(conexion, conversacion_id, mensaje)
                        except Exception:
                            logger.exception("fallo procesando el mensaje")
                            respuesta = None
                    if respuesta is None:
                        st.error(
                            "Tuve un problema procesando su mensaje. Puede deberse a la cuota "
                            "gratuita de Gemini o a la base de datos; intente de nuevo en un momento."
                        )
                    else:
                        st.markdown(respuesta)
    except psycopg.OperationalError as error:
        st.error(f"No pude conectarme a la base de datos: {error}")


if __name__ == "__main__":
    main()
