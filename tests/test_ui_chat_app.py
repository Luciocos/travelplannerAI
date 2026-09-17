"""Tests de ui/chat_app.py con streamlit.testing.v1.AppTest (Fase 7D).

No toca Postgres ni Gemini real: se parchea todo lo que la UI usa por
debajo antes de correr la app, con el mismo criterio del resto de la
suite (ningun test toca la red ni consume cuota de LLM).

Se parchea servicio.py directo (no asistente_viajes.agente/conversaciones
un nivel mas abajo): dentro de servicio.py cada funcion como
`procesar_mensaje(...)` es un nombre resuelto en el namespace GLOBAL del
propio modulo servicio.py en el momento de la llamada, asi que
reasignarlo como atributo del modulo (`servicio.procesar_mensaje = ...`)
sí cambia lo que ejecuta la proxima llamada. Parchear
`asistente_viajes.agente.procesar_mensaje` en cambio solo funciona antes
de la PRIMERA vez que algo hace `from asistente_viajes.agente import
procesar_mensaje` en todo el proceso: `import servicio` en chat_app.py
solo ejecuta el cuerpo de servicio.py una vez (Python cachea modulos en
sys.modules); de ahi en mas cualquier AppTest.run() posterior reusa esa
misma copia ya importada, con el `procesar_mensaje` que haya en ese
momento congelado para siempre en el namespace de servicio.py, sin
importar que se reasigne despues el original en asistente_viajes.agente
(bug real encontrado escribiendo estos tests: un segundo test que
esperaba un error real seguia viendo la respuesta feliz del primero)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from streamlit.testing.v1 import AppTest

from asistente_viajes import db, llm

_DIRECTORIO_UI = Path(__file__).resolve().parent.parent / "ui"
if str(_DIRECTORIO_UI) not in sys.path:
    sys.path.insert(0, str(_DIRECTORIO_UI))

import servicio  # mismo modulo que importa ui/chat_app.py


@contextmanager
def _conexion_falsa():
    yield MagicMock()


def _procesar_mensaje_falso(conexion, rotador, sesion, mensaje):
    """Doble minimo de servicio.procesar_mensaje: solo lo necesario para
    que la UI tenga algo que mostrar y siga funcionando con multiples
    turnos (historial acumulado) dentro de la misma sesion de AppTest."""
    respuesta = f"Respuesta simulada a: {mensaje}"
    sesion.historial.append({"rol": "usuario", "texto": mensaje})
    sesion.historial.append({"rol": "asistente", "texto": respuesta})
    return respuesta


@pytest.fixture(autouse=True)
def _sin_llm_ni_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "crear_rotador", lambda: MagicMock())
    monkeypatch.setattr(db, "obtener_conexion", _conexion_falsa)
    monkeypatch.setattr(servicio, "crear_conversacion", lambda conexion: "chat-1")
    monkeypatch.setattr(servicio, "listar_conversaciones", lambda conexion: [])
    monkeypatch.setattr(servicio, "cargar_conversacion", lambda conexion, id_: None)
    monkeypatch.setattr(servicio, "guardar_turno", lambda *a, **k: None)
    monkeypatch.setattr(servicio, "renombrar_conversacion", lambda *a, **k: None)
    monkeypatch.setattr(servicio, "eliminar_conversacion", lambda *a, **k: None)
    monkeypatch.setattr(servicio, "procesar_mensaje", _procesar_mensaje_falso)


def _app() -> AppTest:
    return AppTest.from_file("../ui/chat_app.py", default_timeout=15)


def test_carga_sin_errores_y_muestra_el_titulo() -> None:
    at = _app().run()

    assert not at.exception
    assert any("Asistente de viajes" in t.value for t in at.title)


def test_chat_vacio_muestra_los_botones_para_arrancar() -> None:
    at = _app().run()

    etiquetas = [b.label for b in at.button]
    assert any("Cancún" in etiqueta for etiqueta in etiquetas)
    assert any("Barcelona" in etiqueta for etiqueta in etiquetas)


def test_clickear_una_sugerencia_manda_el_mensaje_y_muestra_la_respuesta() -> None:
    at = _app().run()
    boton = next(b for b in at.button if "Barcelona" in b.label)

    at = boton.click().run()

    assert not at.exception
    textos = [m.value for m in at.markdown]
    assert any("Barcelona" in t for t in textos)  # el mensaje del usuario
    assert any("Respuesta simulada" in t for t in textos)  # la respuesta del asistente


def test_escribir_un_mensaje_lo_persiste_en_el_historial_entre_turnos() -> None:
    at = _app().run()

    at = at.chat_input[0].set_value("hola, quiero ir a Miami").run()
    assert not at.exception
    assert any("Respuesta simulada" in m.value for m in at.markdown)

    # Un segundo turno en la misma sesion tiene que seguir viendo el
    # historial acumulado (RF11), no arrancar de cero.
    at = at.chat_input[0].set_value("dale, ese").run()
    assert not at.exception
    textos = [m.value for m in at.markdown]
    assert any("hola, quiero ir a Miami" in t for t in textos)
    assert sum("Respuesta simulada" in t for t in textos) == 2


def test_error_al_procesar_el_mensaje_muestra_un_aviso_sin_romper_la_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _falla(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(servicio, "procesar_mensaje", _falla)
    at = _app().run()

    at = at.chat_input[0].set_value("hola").run()

    assert not at.exception  # el error se atrapa, no tira abajo el script
    assert any("problema procesando su mensaje" in e.value for e in at.error)


def test_sin_plan_armado_no_hay_boton_de_descarga() -> None:
    at = _app().run()

    assert len(at.download_button) == 0


def test_nueva_conversacion_no_pierde_la_escritura_por_el_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regresion de P-11: crear un chat nuevo desde la sidebar no puede
    tirar una excepcion (antes, el st.rerun() de dentro del `with
    obtener_conexion()` rompia el flujo)."""
    ids_creados = iter(["chat-1", "chat-2"])
    monkeypatch.setattr(servicio, "crear_conversacion", lambda conexion: next(ids_creados))

    at = _app().run()
    boton_nueva = next(b for b in at.sidebar.button if "Nueva conversación" in b.label)

    at = boton_nueva.click().run()

    assert not at.exception
