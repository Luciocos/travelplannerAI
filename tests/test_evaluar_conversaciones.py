"""Tests de la logica determinista de evaluar_conversaciones.py (Fase 7D).

No corre ningun escenario contra el LLM real (eso es exactamente lo que
el harness hace a mano, nunca en CI): solo prueba _verificar_turno,
ejecutar_escenario (con un procesar_mensaje mockeado) y el reporte."""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts import evaluar_conversaciones as mod


def test_verificar_turno_detecta_lo_que_falta() -> None:
    spec = {"debe_contener": ["Barcelona", "medio"]}

    fallas = mod._verificar_turno("Le recomiendo Barcelona con presupuesto alto.", spec)

    assert len(fallas) == 1
    assert "medio" in fallas[0]


def test_verificar_turno_detecta_lo_que_no_deberia_estar() -> None:
    spec = {"no_debe_contener": ["no tengo esa información"]}

    fallas = mod._verificar_turno("No tengo esa información sobre eso.", spec)

    assert len(fallas) == 1


def test_verificar_turno_sin_fallas_cuando_todo_se_cumple() -> None:
    spec = {"debe_contener": ["Cancún"], "no_debe_contener": ["Tokio"]}

    fallas = mod._verificar_turno("Le armo un plan para Cancún.", spec)

    assert fallas == []


def test_verificar_turno_es_insensible_a_mayusculas() -> None:
    spec = {"debe_contener": ["cancún"]}

    fallas = mod._verificar_turno("Le armo un plan para CANCÚN.", spec)

    assert fallas == []


def test_ejecutar_escenario_marca_ok_cuando_todos_los_turnos_pasan(monkeypatch) -> None:
    monkeypatch.setattr(mod, "procesar_mensaje", lambda *a, **k: "Le recomiendo Barcelona.")
    escenario = {
        "nombre": "test",
        "turnos": [{"mensaje": "hola", "debe_contener": ["Barcelona"]}],
    }

    resultado = mod.ejecutar_escenario(MagicMock(), MagicMock(), escenario, pausa=0)

    assert resultado.ok
    assert resultado.turnos[0].respuesta == "Le recomiendo Barcelona."


def test_ejecutar_escenario_marca_falla_sin_interrumpir_los_demas_turnos(monkeypatch) -> None:
    respuestas = iter(["le recomiendo Miami", "le recomiendo Cancún"])
    monkeypatch.setattr(mod, "procesar_mensaje", lambda *a, **k: next(respuestas))
    escenario = {
        "nombre": "test",
        "turnos": [
            {"mensaje": "uno", "debe_contener": ["Barcelona"]},
            {"mensaje": "dos", "debe_contener": ["Cancún"]},
        ],
    }

    resultado = mod.ejecutar_escenario(MagicMock(), MagicMock(), escenario, pausa=0)

    assert not resultado.ok
    assert not resultado.turnos[0].ok
    assert resultado.turnos[1].ok


def test_ejecutar_escenario_reporta_una_excepcion_como_falla_del_turno(monkeypatch) -> None:
    def _falla(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "procesar_mensaje", _falla)
    escenario = {"nombre": "test", "turnos": [{"mensaje": "hola"}]}

    resultado = mod.ejecutar_escenario(MagicMock(), MagicMock(), escenario, pausa=0)

    assert not resultado.ok
    assert "excepción" in resultado.turnos[0].fallas[0]


def test_reporte_markdown_incluye_el_resumen_y_las_fallas() -> None:
    resultados = [
        mod.ResultadoEscenario(
            nombre="recap_memoria",
            turnos=[mod.ResultadoTurno("hola", "Barcelona", fallas=[])],
        ),
        mod.ResultadoEscenario(
            nombre="otro",
            turnos=[mod.ResultadoTurno("chau", "algo", fallas=['esperaba encontrar "Miami"'])],
        ),
    ]

    reporte = mod._reporte_markdown(resultados)

    assert "1/2 turnos OK en 2 escenario(s)." in reporte
    assert "recap_memoria" in reporte
    assert 'esperaba encontrar "Miami"' in reporte


def test_escenarios_json_tiene_la_forma_esperada() -> None:
    import json

    escenarios = json.loads(mod.RUTA_ESCENARIOS.read_text(encoding="utf-8"))

    assert len(escenarios) >= 5
    for escenario in escenarios:
        assert escenario["nombre"]
        assert escenario["turnos"]
        for turno in escenario["turnos"]:
            assert turno["mensaje"]
