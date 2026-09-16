"""Tests de recomendar_actividades y recomendar_locales (RF3, RF4),
llamadas directo sin agente (ver plan-de-fases.md, criterio de Fase 3).
Mockea la recuperacion y el LLM, no toca la red ni Postgres real."""

from __future__ import annotations

from unittest.mock import MagicMock

from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.tools import recomendar_actividades as mod_actividades
from asistente_viajes.tools import recomendar_locales as mod_locales
from asistente_viajes.tools import responder_faq_viajero as mod_faq


def _rotador_falso(respuesta_texto: str = "Justificación de prueba.") -> MagicMock:
    rotador = MagicMock()
    rotador.invocar.return_value = MagicMock(content=respuesta_texto)
    return rotador


def test_recomendar_actividades_justifica_solo_con_el_texto_recuperado(
    monkeypatch,
) -> None:
    resultado = ResultadoRecuperado(
        nombre="Museo de Arqueologia de Alta Montaña",
        categoria="museums",
        texto="Texto real recuperado del corpus.",
    )
    monkeypatch.setattr(mod_actividades, "buscar_atractivos", lambda *_, **__: [resultado])

    rotador = _rotador_falso()
    actividades = mod_actividades.recomendar_actividades(
        conexion=MagicMock(), rotador=rotador, destino="Salta", intereses=["historia"]
    )

    assert len(actividades) == 1
    assert actividades[0].nombre == "Museo de Arqueologia de Alta Montaña"
    assert actividades[0].justificacion == "Justificación de prueba."

    prompt_enviado = rotador.invocar.call_args.args[0]
    assert "Texto real recuperado del corpus." in prompt_enviado
    assert "no agregue datos" in prompt_enviado.lower()


def test_recomendar_locales_incluye_direccion_y_precio(monkeypatch) -> None:
    resultado = ResultadoRecuperado(
        nombre="Mercado Artesanal",
        categoria="shops",
        texto="Texto real del comercio.",
        direccion="Av. San Martin 2555",
        rango_precio="$$",
    )
    monkeypatch.setattr(mod_locales, "buscar_comercios", lambda *_, **__: [resultado])

    rotador = _rotador_falso("Buena opción para lo que pediste.")
    locales = mod_locales.recomendar_locales(
        conexion=MagicMock(), rotador=rotador, destino="Salta", consulta="artesanias"
    )

    assert len(locales) == 1
    assert locales[0].direccion == "Av. San Martin 2555"
    assert locales[0].rango_precio == "$$"


def test_tool_recomendar_actividades_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_actividades.crear_tool_recomendar_actividades(
        conexion=MagicMock(), rotador=_rotador_falso()
    )

    assert tool_creada.name == "recomendar_actividades"
    assert tool_creada.description  # el agente lee esto para decidir cuando llamarla
    assert tool_creada.args_schema is mod_actividades.ArgsRecomendarActividades


def test_tool_recomendar_locales_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_locales.crear_tool_recomendar_locales(
        conexion=MagicMock(), rotador=_rotador_falso()
    )

    assert tool_creada.name == "recomendar_locales"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_locales.ArgsRecomendarLocales


def test_responder_faq_viajero_responde_solo_con_el_texto_recuperado(monkeypatch) -> None:
    resultado = ResultadoRecuperado(
        nombre="Taxis y tarifas",
        categoria="estafas",
        texto="Texto real del corpus de FAQ.",
    )
    monkeypatch.setattr(mod_faq, "buscar_faq", lambda *_, **__: [resultado])

    rotador = _rotador_falso("En Cancun conviene acordar el precio antes de subir.")
    respuestas = mod_faq.responder_faq_viajero(
        conexion=MagicMock(), rotador=rotador, destino="Cancun", consulta="es seguro tomar un taxi"
    )

    assert len(respuestas) == 1
    assert respuestas[0].tema == "Taxis y tarifas"
    assert respuestas[0].respuesta == "En Cancun conviene acordar el precio antes de subir."

    prompt_enviado = rotador.invocar.call_args.args[0]
    assert "Texto real del corpus de FAQ." in prompt_enviado
    assert "no agregue datos" in prompt_enviado.lower()


def test_tool_responder_faq_viajero_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_faq.crear_tool_responder_faq_viajero(
        conexion=MagicMock(), rotador=_rotador_falso()
    )

    assert tool_creada.name == "responder_faq_viajero"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_faq.ArgsResponderFaqViajero
