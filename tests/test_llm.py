"""Tests de contenido_texto (llm.py). No toca la red.

Bug real encontrado el 2026-09-10: gemini-3.5-flash-lite devuelve
`.content` como una lista de bloques `{'type': 'text', 'text': ...}`,
no como string plano (formato que asumian completar_slots,
recomendar_actividades y recomendar_locales antes de este fix)."""

from __future__ import annotations

from unittest.mock import MagicMock

from asistente_viajes.config import Configuracion
from asistente_viajes.llm import (
    MAX_REINTENTOS_SDK,
    TIMEOUT_SEGUNDOS_LLM,
    RotadorClavesGemini,
    _es_error_cuota,
    _es_limite_diario,
    contenido_texto,
    crear_rotador,
)


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


def test_es_error_cuota_detecta_429_y_503() -> None:
    """P-06: el SDK de google-genai reintenta un 503/UNAVAILABLE con el
    mismo backoff exponencial que un 429 agotado, asi que el rotador tiene
    que tratarlos igual para rotar de key en vez de esperar el reintento
    interno del SDK."""
    assert _es_error_cuota(Exception("429 Too Many Requests")) is True
    assert _es_error_cuota(Exception("503 Service Unavailable")) is True
    assert _es_error_cuota(Exception("UNAVAILABLE: overloaded")) is True
    assert _es_error_cuota(Exception("400 Bad Request")) is False


def test_es_limite_diario_no_confunde_503_con_limite_diario() -> None:
    assert _es_limite_diario(Exception("503 Service Unavailable")) is False


def test_crear_rotador_limita_reintentos_del_sdk_y_el_timeout() -> None:
    """El rotador propio (rotar de key) tiene que ganarle al reintento
    interno del SDK (misma key, backoff exponencial ~1+2+4+8+16s), o el
    failover nunca se nota y una key agotada tarda decenas de segundos en
    vez de fallar rapido (P-06 en DIFICULTADES.md)."""
    configuracion = Configuracion(
        llm_provider="gemini", gemini_model="gemini-3.5-flash-lite", claves_gemini=["clave-1"]
    )

    rotador = crear_rotador(configuracion)

    assert isinstance(rotador, RotadorClavesGemini)
    assert rotador._kwargs_modelo == {
        "max_retries": MAX_REINTENTOS_SDK,
        "timeout": TIMEOUT_SEGUNDOS_LLM,
    }
