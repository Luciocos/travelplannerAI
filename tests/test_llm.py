"""Tests de contenido_texto (llm.py). No toca la red.

Bug real encontrado el 2026-09-10: gemini-3.5-flash-lite devuelve
`.content` como una lista de bloques `{'type': 'text', 'text': ...}`,
no como string plano (formato que asumian completar_slots,
recomendar_actividades y recomendar_locales antes de este fix)."""

from __future__ import annotations

from unittest.mock import MagicMock

from asistente_viajes.llm import contenido_texto


def test_contenido_texto_con_string_plano() -> None:
    respuesta = MagicMock(content="  hola  ")

    assert contenido_texto(respuesta) == "hola"


def test_contenido_texto_con_lista_de_bloques() -> None:
    respuesta = MagicMock(content=[{"type": "text", "text": "hola", "extras": {"signature": "x"}}])

    assert contenido_texto(respuesta) == "hola"


def test_contenido_texto_con_varios_bloques_de_texto_los_concatena() -> None:
    respuesta = MagicMock(
        content=[{"type": "text", "text": "hola "}, {"type": "text", "text": "mundo"}]
    )

    assert contenido_texto(respuesta) == "hola mundo"


def test_contenido_texto_ignora_bloques_que_no_son_de_texto() -> None:
    respuesta = MagicMock(
        content=[{"type": "text", "text": "hola"}, {"type": "signature", "data": "xyz"}]
    )

    assert contenido_texto(respuesta) == "hola"


def test_contenido_texto_sin_content_usa_str_de_la_respuesta() -> None:
    assert contenido_texto("respuesta cruda") == "respuesta cruda"
