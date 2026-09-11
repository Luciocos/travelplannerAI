"""Tests del adaptador de Fly Scraper, reducido a price-calendar (ver
migracion-amadeus-a-rapidapi.md, addendum). Mockea client.llamar, no toca
la red ni Postgres real."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from asistente_viajes.services.rapidapi import client
from asistente_viajes.services.rapidapi import fly_scraper as mod

RUTA_FIXTURES = Path(__file__).resolve().parent.parent / "src" / "asistente_viajes" / "services" / "rapidapi" / "fixtures"


@pytest.fixture(autouse=True)
def _configuracion_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ver el mismo fixture en test_booking.py: cargar_configuracion()
    exige variables que este modulo no usa."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY_1", "clave-de-prueba")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test")
    monkeypatch.setenv("RAPIDAPI_KEY", "clave-rapidapi-de-prueba")


def _cargar_fixture(nombre: str) -> dict:
    return json.loads((RUTA_FIXTURES / nombre).read_text(encoding="utf-8"))


def test_a_precio_por_dia_parsea_registro_real() -> None:
    body = _cargar_fixture("fly_scraper_v2_flights_price-calendar.json")
    registro_crudo = body["data"][0]

    precio = mod._a_precio_por_dia(registro_crudo)

    assert precio.dia
    assert precio.precio is not None
    assert precio.moneda
    assert not precio.es_fixture


def test_a_precio_por_dia_con_campos_faltantes_no_rompe() -> None:
    precio = mod._a_precio_por_dia({})

    assert precio.dia == ""
    assert precio.precio is None
    assert precio.aerolinea is None


def test_calendario_precios_llamada_exitosa(monkeypatch) -> None:
    body = _cargar_fixture("fly_scraper_v2_flights_price-calendar.json")
    monkeypatch.setattr(client, "llamar", lambda *_, **__: body)

    resultado = mod.calendario_precios(MagicMock(), "BCN", "CUN")

    assert resultado
    assert all(not precio.es_fixture for precio in resultado)


def test_calendario_precios_usa_fixture_si_falla(monkeypatch) -> None:
    monkeypatch.setattr(client, "llamar", MagicMock(side_effect=client.ErrorCuotaAgotada("sin cuota")))

    resultado = mod.calendario_precios(MagicMock(), "BCN", "CUN")

    assert resultado
    assert all(precio.es_fixture for precio in resultado)
