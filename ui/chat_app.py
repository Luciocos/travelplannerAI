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
    """El id de la conversacion activa. session_state es la UNICA fuente
    de verdad mientras dura esta sesion de navegador; st.query_params se
    lee solo una vez, en la primera carga (para que un refresh de pagina
    no pierda el chat), y de ahi en mas solo se escribe, nunca se vuelve
    a leer.

    Bug real encontrado probando la app: escribir en st.query_params y
    confiar en volver a leerlo en el rerun inmediato siguiente (por
    ejemplo, el que dispara el propio boton "Nueva conversacion") no
    garantiza ver el valor nuevo a tiempo — el round-trip con el
    navegador no es instantaneo — asi que ese rerun llegaba a crear una
    SEGUNDA conversacion sin darse cuenta, y el siguiente mensaje fallaba
    al guardarse (violacion de foreign key contra un id que nunca quedo
    confirmado). La solucion es no depender de esa lectura de vuelta:
    cualquier cambio de chat escribe session_state directo (ver
    _cambiar_de_chat), nunca lo borra para forzar una relectura."""
    if "chat_actual" not in st.session_state:
        id_en_url = st.query_params.get("c")
        st.session_state.chat_actual = id_en_url or servicio.nueva_conversacion(conexion)
        st.query_params["c"] = st.session_state.chat_actual
    return st.session_state.chat_actual


def _cambiar_de_chat(conversacion_id: str) -> None:
    st.session_state.chat_actual = conversacion_id
    st.query_params["c"] = conversacion_id
    st.session_state.pop("sesion", None)
    st.session_state.pop("renombrando", None)


def _sidebar(conexion, conversacion_id: str) -> bool:
    """Devuelve True si hace falta un st.rerun() despues. Nunca lo llama
    aca directo: este codigo corre DENTRO de un `with obtener_conexion()`
    (ver main()), y st.rerun() funciona lanzando una excepcion de control
    interna de Streamlit — si esa excepcion se lanza dentro del `with`,
    el manejador `except Exception: conexion.rollback()` de
    obtener_conexion() la trata como un error y DESHACE cualquier
    escritura recien hecha (crear/eliminar/renombrar un chat), en vez de
    dejar que el `with` cierre solo y confirme. Bug real encontrado
    probando la app: crear un chat nuevo o cambiar de chat se veia bien
    en la UI (session_state ya tenia el id nuevo en memoria) pero nunca
    quedaba guardado en Postgres, y el primer mensaje de ese chat fallaba
    al guardarse con una violacion de foreign key contra un id que nunca
    se confirmo."""
    necesita_rerun = False
    with st.sidebar:
        if st.button("➕ Nueva conversación", width="stretch"):
            _cambiar_de_chat(servicio.nueva_conversacion(conexion))
            necesita_rerun = True

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
                    necesita_rerun = True
            with columnas[1]:
                if st.button("✏️", key=f"renombrar_{chat.id}", help="Renombrar"):
                    st.session_state["renombrando"] = chat.id
            with columnas[2]:
                if st.button("🗑️", key=f"borrar_{chat.id}", help="Eliminar"):
                    servicio.eliminar_chat(conexion, chat.id)
                    if es_actual:
                        _cambiar_de_chat(servicio.nueva_conversacion(conexion))
                    necesita_rerun = True

            if st.session_state.get("renombrando") == chat.id:
                nuevo_titulo = st.text_input(
                    "Nuevo título", value=chat.titulo, key=f"titulo_{chat.id}"
                )
                col_ok, col_cancelar = st.columns(2)
                if col_ok.button("Guardar", key=f"guardar_titulo_{chat.id}"):
                    servicio.renombrar_chat(conexion, chat.id, nuevo_titulo)
                    del st.session_state["renombrando"]
                    necesita_rerun = True
                if col_cancelar.button("Cancelar", key=f"cancelar_titulo_{chat.id}"):
                    del st.session_state["renombrando"]
                    necesita_rerun = True
    return necesita_rerun


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


def _cuerpo_principal(conexion) -> bool:
    """Todo lo que corre dentro del `with obtener_conexion()` de main().
    Devuelve True si hace falta un st.rerun() (ver _sidebar): nunca lo
    llama directo, para que la conexion pueda cerrar y confirmar sola."""
    conversacion_id = _chat_activo(conexion)

    if "sesion" not in st.session_state:
        # _chat_activo ya fijo chat_actual; _cambiar_de_chat borra
        # "sesion" a proposito para forzar esta recarga cuando se
        # cambia de chat (ver ese docstring).
        st.session_state.sesion = servicio.cargar_chat(conexion, conversacion_id)

    if _sidebar(conexion, conversacion_id):
        # Cortamos aca: nada de lo que sigue (mensajes, boton de
        # descarga, chat_input) depende de un rerun ya decidido, y
        # seguir pintando con el conversacion_id viejo daria un frame de
        # transicion inconsistente.
        return True

    for turno in st.session_state.sesion.historial:
        es_usuario = turno["rol"] == "usuario"
        with st.chat_message("user" if es_usuario else "assistant"):
            # El HTML (tarjetas de plan/actividades/etc, ver presentacion.py)
            # solo lo genera el asistente, con todo dato dinamico ya
            # escapado; el texto del usuario nunca se renderiza como HTML.
            st.markdown(turno["texto"], unsafe_allow_html=not es_usuario)

    itinerario_md = servicio.itinerario_descargable(st.session_state.sesion)
    if itinerario_md:
        st.download_button(
            "⬇️ Descargar itinerario",
            data=itinerario_md,
            file_name=f"itinerario_{st.session_state.sesion.estado.destino or 'viaje'}.md",
            mime="text/markdown",
        )

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
                st.markdown(respuesta, unsafe_allow_html=True)
    return False


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
            necesita_rerun = _cuerpo_principal(conexion)
    except psycopg.OperationalError as error:
        st.error(f"No pude conectarme a la base de datos: {error}")
        return

    if necesita_rerun:
        st.rerun()


if __name__ == "__main__":
    main()
