"""Tests de completar_slots (RF1, RF2). Mockea el rotador de LLM, no toca
la red ni consume cuota de Gemini."""

from __future__ import annotations

from unittest.mock import MagicMock

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.tools.completar_slots import (
    _destino_fue_inferido,
    completar_slots,
    crear_tool_completar_slots,
)


def _rotador_falso(slots_extraidos: PreferenciasViaje, pregunta: str = "¿Cuántas personas viajan?"):
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = slots_extraidos
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    rotador.invocar.return_value = MagicMock(content=pregunta)
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


def test_completar_slots_no_pisa_lo_ya_cargado() -> None:
    estado_actual = PreferenciasViaje(destino="Miami")
    extraidos = PreferenciasViaje(cantidad_personas=2)
    rotador = _rotador_falso(extraidos)

    estado, _ = completar_slots(rotador, "somos 2 personas", estado_actual)

    assert estado.destino == "Miami"
    assert estado.cantidad_personas == 2


def test_completar_slots_no_pregunta_si_ya_esta_todo_completo() -> None:
    from datetime import date

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
    rotador.invocar.assert_not_called()


def test_completar_slots_pregunta_maximo_dos_por_turno() -> None:
    rotador = _rotador_falso(PreferenciasViaje())

    completar_slots(rotador, "hola", PreferenciasViaje())

    prompt_enviado = rotador.invocar.call_args.args[0]
    # Con estado vacio hay 7 faltantes (orden fijo en SLOTS_OBLIGATORIOS),
    # solo se pregunta por los 2 primeros: destino y tipo_destino.
    assert "el destino" in prompt_enviado
    assert "el tipo de destino" in prompt_enviado
    assert "los intereses" not in prompt_enviado
    assert "la cantidad de personas" not in prompt_enviado


def test_destino_fue_inferido_si_no_esta_literal_en_el_mensaje() -> None:
    assert _destino_fue_inferido("quiero un lugar caribeño", "Cancun") is True


def test_destino_no_fue_inferido_si_esta_literal_insensible_a_tildes() -> None:
    assert _destino_fue_inferido("quiero ir a Cancún", "Cancun") is False
    assert _destino_fue_inferido("quiero ir a CANCUN de vacaciones", "Cancun") is False


def test_completar_slots_confirma_destino_inferido_con_todo_lo_demas_completo() -> None:
    from datetime import date

    extraidos = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["descanso"],
        presupuesto="medio",
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 3),
        cantidad_personas=2,
    )
    rotador = _rotador_falso(extraidos, pregunta="¿Te referís a Cancún?")

    estado, pregunta = completar_slots(rotador, "quiero un lugar caribeño", PreferenciasViaje())

    assert estado.destino == "Cancun"
    assert pregunta == "¿Te referís a Cancún?"
    rotador.invocar.assert_called_once()
    prompt_enviado = rotador.invocar.call_args.args[0]
    assert "Cancun" in prompt_enviado


def test_completar_slots_no_confirma_si_destino_esta_literal_en_el_mensaje() -> None:
    from datetime import date

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
    rotador.invocar.assert_not_called()


def test_tool_completar_slots_tiene_docstring_y_args_schema() -> None:
    tool_creada = crear_tool_completar_slots(_rotador_falso(PreferenciasViaje()))

    assert tool_creada.name == "completar_slots"
    assert tool_creada.description
