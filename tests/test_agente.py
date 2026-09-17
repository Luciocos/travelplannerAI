"""Tests de la fachada del orquestador (agente.py, RF11, Fase 7C).

La logica del orquestador en si (que accion corresponde, como se arma la
respuesta) vive en grafo.py y esta testeada en test_grafo.py. Aca solo se
prueba que SesionAgente/procesar_mensaje traducen correctamente entre la
memoria de sesion y grafo.procesar_turno. Mockea grafo.procesar_turno, no
toca la red ni Postgres real."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from asistente_viajes import agente as mod
from asistente_viajes.estado import PreferenciasViaje


def _resultado_grafo(**overrides) -> dict:
    base = {
        "estado": PreferenciasViaje(destino="Cancun").model_dump(mode="json"),
        "ultimo_plan": None,
        "info_destino_mostrada_para": None,
        "respuesta_texto": "¿Qué le interesa hacer?",
    }
    base.update(overrides)
    return base


def test_procesar_mensaje_actualiza_la_sesion_con_el_resultado_del_grafo(monkeypatch) -> None:
    resultado = _resultado_grafo(
        ultimo_plan={"destino": "Cancun"}, info_destino_mostrada_para="Cancun"
    )
    monkeypatch.setattr(mod, "procesar_turno", lambda **_: resultado)

    sesion = mod.SesionAgente()
    respuesta = mod.procesar_mensaje(MagicMock(), MagicMock(), sesion, "quiero ir a Cancun")

    assert respuesta == "¿Qué le interesa hacer?"
    assert sesion.estado.destino == "Cancun"
    assert sesion.ultimo_plan == {"destino": "Cancun"}
    assert sesion.info_destino_mostrada_para == "Cancun"


def test_procesar_mensaje_guarda_el_turno_en_el_historial(monkeypatch) -> None:
    monkeypatch.setattr(mod, "procesar_turno", lambda **_: _resultado_grafo())

    sesion = mod.SesionAgente()
    mod.procesar_mensaje(MagicMock(), MagicMock(), sesion, "hola")

    assert sesion.historial[-2] == {"rol": "usuario", "texto": "hola"}
    assert sesion.historial[-1] == {"rol": "asistente", "texto": "¿Qué le interesa hacer?"}


def test_procesar_mensaje_pasa_la_sesion_actual_al_grafo(monkeypatch) -> None:
    capturado = {}

    def _falso_procesar_turno(**kwargs):
        capturado.update(kwargs)
        capturado["historial"] = list(
            kwargs["historial"]
        )  # copia: la sesion sigue mutando la lista original
        return _resultado_grafo()

    monkeypatch.setattr(mod, "procesar_turno", _falso_procesar_turno)

    estado_previo = PreferenciasViaje(destino="Miami", cantidad_personas=2)
    sesion = mod.SesionAgente(
        estado=estado_previo,
        historial=[{"rol": "usuario", "texto": "hola"}, {"rol": "asistente", "texto": "hola!"}],
        ultimo_plan={"destino": "Miami"},
        info_destino_mostrada_para="Miami",
    )

    mod.procesar_mensaje(MagicMock(), MagicMock(), sesion, "somos 3", hoy=date(2026, 9, 17))

    assert capturado["mensaje"] == "somos 3"
    assert capturado["estado"]["destino"] == "Miami"
    assert capturado["ultimo_plan"] == {"destino": "Miami"}
    assert capturado["info_destino_mostrada_para"] == "Miami"
    assert len(capturado["historial"]) == 2
    assert capturado["hoy"] == date(2026, 9, 17)


def test_procesar_mensaje_recorta_el_historial_guardado(monkeypatch) -> None:
    monkeypatch.setattr(mod, "procesar_turno", lambda **_: _resultado_grafo())

    sesion = mod.SesionAgente()
    cantidad_turnos = mod.TURNOS_DE_HISTORIAL_GUARDADOS  # cada turno agrega 2 entradas
    for i in range(cantidad_turnos):
        mod.procesar_mensaje(MagicMock(), MagicMock(), sesion, f"mensaje {i}")

    assert len(sesion.historial) == cantidad_turnos
    assert sesion.historial[-2]["texto"] == f"mensaje {cantidad_turnos - 1}"
