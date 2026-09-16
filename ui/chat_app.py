"""GUI de demo del asistente de viajes (Streamlit, Fase 7B).

Capa de presentacion pura: importa SesionAgente/procesar_mensaje de
asistente_viajes.agente, igual que scripts/chat.py y el notebook. No
agrega logica de negocio nueva. No es el entregable oficial (el notebook
lo es, ver consigna-catedra.md); se agrego por pedido explicito del
usuario para que la demo se vea mejor que el CLI de texto plano.

Uso: streamlit run ui/chat_app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from asistente_viajes.agente import SesionAgente, procesar_mensaje
from asistente_viajes.config import ConfiguracionInvalida
from asistente_viajes.db import obtener_conexion
from asistente_viajes.llm import crear_rotador

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

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


def _inicializar_estado() -> None:
    if "sesion" not in st.session_state:
        st.session_state.sesion = SesionAgente()
    if "historial" not in st.session_state:
        st.session_state.historial = []


def _responder(mensaje: str) -> str:
    with obtener_conexion() as conexion:
        return procesar_mensaje(conexion, _rotador(), st.session_state.sesion, mensaje)


def main() -> None:
    st.title("🧳 Asistente de viajes")
    st.caption("Destinos piloto: Barcelona, Miami o Cancún. Cuénteme qué viaje está buscando.")

    try:
        _rotador()
    except ConfiguracionInvalida as error:
        st.error(f"Error de configuración: {error}")
        return

    _inicializar_estado()

    mensaje_de_boton = None
    with st.sidebar:
        st.subheader("Para arrancar")
        st.caption(
            "Estos botones mandan el mismo texto que escribirías a mano: el orquestador sigue decidiendo solo qué tool usar (RF12)."
        )
        for opcion in OPCIONES_PREDEFINIDAS:
            if st.button(opcion, use_container_width=True, key=opcion):
                mensaje_de_boton = opcion

    for turno in st.session_state.historial:
        with st.chat_message(turno["rol"]):
            st.markdown(turno["contenido"])

    mensaje_escrito = st.chat_input("Escriba su mensaje...")
    mensaje = mensaje_de_boton or mensaje_escrito

    if mensaje:
        st.session_state.historial.append({"rol": "user", "contenido": mensaje})
        with st.chat_message("user"):
            st.markdown(mensaje)
        with st.chat_message("assistant"):
            with st.spinner(
                "Pensando... (puede tardar, la cuota gratis de Gemini a veces anda lenta)"
            ):
                respuesta = _responder(mensaje)
            st.markdown(respuesta)
        st.session_state.historial.append({"rol": "assistant", "contenido": respuesta})


if __name__ == "__main__":
    main()
