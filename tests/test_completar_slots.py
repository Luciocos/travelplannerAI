"""Tests de completar_slots (RF1, RF2). Mockea el rotador de LLM, no toca
la red ni consume cuota de Gemini. Desde D-14 la pregunta por lo que
falta es deterministica (preguntas.py), no pasa por el LLM."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.tools.completar_slots import (
    _destino_fue_inferido,
    completar_slots,
    crear_tool_completar_slots,
)


def _rotador_falso(slots_extraidos: PreferenciasViaje) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = slots_extraidos
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    return rotador


def test_completar_slots_fusiona_y_pregunta_lo_que_falta() -> None:
    extraidos = PreferenciasViaje(intereses=["caminatas", "historia"], presupuesto="medio")
    rotador = _rotador_falso(extraidos)

    estado, pregunta = completar_slots(
        rotador, "quiero caminar y ver historia, presupuesto medio", PreferenciasViaje()
    )

    assert estado.intereses == ["caminatas", "historia"]
    assert estado.presupuesto == "medio"
    assert pregunta is not None
    rotador.con_salida_estructurada.assert_called_once_with(PreferenciasViaje)


def test_prompt_extraccion_aclara_que_caracteristicas_no_son_gustos_del_usuario() -> None:
    """Regresion: el LLM real llego a copiar las caracteristicas del
    destino inferido (dadas solo para identificar la ciudad) como si
    fueran tipo_destino/intereses del usuario, violando 'nada inventado'
    (restriccion 5). El prompt tiene que dejarlo explicito."""
    rotador = _rotador_falso(PreferenciasViaje())

    completar_slots(rotador, "quiero ir de viaje 7 dias a europa", PreferenciasViaje())

    prompt_enviado = rotador.con_salida_estructurada.return_value.invoke.call_args.args[0]
    assert "nunca las copies en tipo_destino ni en intereses" in prompt_enviado


def test_completar_slots_no_pisa_lo_ya_cargado() -> None:
    estado_actual = PreferenciasViaje(destino="Miami")
    extraidos = PreferenciasViaje(cantidad_personas=2)
    rotador = _rotador_falso(extraidos)

    estado, _ = completar_slots(rotador, "somos 2 personas", estado_actual)

    assert estado.destino == "Miami"
    assert estado.cantidad_personas == 2


def test_completar_slots_no_pregunta_si_ya_esta_todo_completo() -> None:
    estado_actual = PreferenciasViaje(
        destino="Miami",
        tipo_destino="playa",
        intereses=["compras"],
        presupuesto="medio",
        fecha_inicio=date(2026, 12, 1),
        fecha_fin=date(2026, 12, 10),
        cantidad_personas=2,
    )
    rotador = _rotador_falso(PreferenciasViaje())

    estado, pregunta = completar_slots(rotador, "listo", estado_actual)

    assert pregunta is None
    assert estado.completo()


def test_completar_slots_deriva_tipo_destino_del_destino_confirmado() -> None:
    """D-14: tipo_destino nunca se pregunta aparte, se deriva del destino
    piloto en cuanto esta confirmado."""
    extraidos = PreferenciasViaje(destino="Cancun")
    rotador = _rotador_falso(extraidos)

    estado, pregunta = completar_slots(rotador, "quiero ir a Cancun", PreferenciasViaje())

    assert estado.tipo_destino == "playa"
    assert pregunta is not None
    assert "tipo de destino" not in pregunta.lower()


def test_completar_slots_pregunta_es_una_sola_con_todo_lo_que_falta() -> None:
    rotador = _rotador_falso(PreferenciasViaje())

    _, pregunta = completar_slots(rotador, "hola", PreferenciasViaje())

    assert "Barcelona" in pregunta
    assert "historia" in pregunta
    assert "usar sugerencias" in pregunta


def test_destino_fue_inferido_si_no_esta_literal_en_el_mensaje() -> None:
    assert _destino_fue_inferido("quiero un lugar caribeño", "Cancun") is True


def test_destino_no_fue_inferido_si_esta_literal_insensible_a_tildes() -> None:
    assert _destino_fue_inferido("quiero ir a Cancún", "Cancun") is False
    assert _destino_fue_inferido("quiero ir a CANCUN de vacaciones", "Cancun") is False


def test_completar_slots_confirma_destino_inferido_con_todo_lo_demas_completo() -> None:
    extraidos = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["descanso"],
        presupuesto="medio",
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 3),
        cantidad_personas=2,
    )
    rotador = _rotador_falso(extraidos)

    estado, pregunta = completar_slots(rotador, "quiero un lugar caribeño", PreferenciasViaje())

    assert estado.destino == "Cancun"
    assert pregunta == "Perfecto, entonces Cancun. Avíseme si no es así."


def test_completar_slots_no_confirma_si_destino_esta_literal_en_el_mensaje() -> None:
    extraidos = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["descanso"],
        presupuesto="medio",
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 3),
        cantidad_personas=2,
    )
    rotador = _rotador_falso(extraidos)

    estado, pregunta = completar_slots(rotador, "quiero ir a Cancun", PreferenciasViaje())

    assert estado.completo()
    assert pregunta is None


def test_tool_completar_slots_tiene_docstring_y_args_schema() -> None:
    tool_creada = crear_tool_completar_slots(_rotador_falso(PreferenciasViaje()))

    assert tool_creada.name == "completar_slots"
    assert tool_creada.description
