"""Tests del adaptador de Booking.com15 (RF6/RF7, D-06). Los parsers se
prueban contra fixtures con respuestas reales grabadas (ver
migracion-amadeus-a-rapidapi.md, seccion 6), nunca contra datos supuestos.
Mockea client.llamar y el cache, no toca la red ni Postgres real."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from asistente_viajes.services.rapidapi import booking as mod
from asistente_viajes.services.rapidapi import client
from asistente_viajes.services.rapidapi.models import DestinoResuelto

RUTA_FIXTURES = Path(__file__).resolve().parent.parent / "src" / "asistente_viajes" / "services" / "rapidapi" / "fixtures"


@pytest.fixture(autouse=True)
def _configuracion_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """cargar_configuracion() exige LLM_PROVIDER/GEMINI_MODEL/etc aunque el
    modulo bajo test no los use (un solo objeto Configuracion global, ver
    config.py). Sin esto, cualquier test que dispare cargar_configuracion()
    revienta con lo que haya (o no) en el .env real de quien corre los tests."""
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    monkeypatch.setenv("GEMINI_API_KEY_1", "clave-de-prueba")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test")
    monkeypatch.setenv("RAPIDAPI_KEY", "clave-rapidapi-de-prueba")


def _cargar_fixture(nombre: str) -> dict:
    return json.loads((RUTA_FIXTURES / nombre).read_text(encoding="utf-8"))


def test_a_alojamiento_parsea_hotel_real() -> None:
    body = _cargar_fixture("booking_searchHotels_barcelona.json")
    hotel_crudo = body["data"]["hotels"][0]

    alojamiento = mod._a_alojamiento(hotel_crudo)

    assert alojamiento.nombre
    assert alojamiento.proveedor == "booking"
    assert alojamiento.precio_total is not None
    assert alojamiento.moneda
    assert alojamiento.puntaje is not None


def test_a_alojamiento_con_campos_faltantes_no_rompe() -> None:
    alojamiento = mod._a_alojamiento({"property": {"name": "Hotel Minimo"}})

    assert alojamiento.nombre == "Hotel Minimo"
    assert alojamiento.precio_total is None
    assert alojamiento.direccion is None


def test_a_alojamiento_sin_property_no_rompe() -> None:
    alojamiento = mod._a_alojamiento({})

    assert alojamiento.nombre == "Alojamiento sin nombre"


def test_a_opcion_vuelo_parsea_oferta_real() -> None:
    body = _cargar_fixture("booking_flights_searchFlights_bue_cun.json")
    oferta_cruda = body["data"]["flightOffers"][0]

    vuelo = mod._a_opcion_vuelo(oferta_cruda)

    assert vuelo.proveedor == "booking"
    assert vuelo.origen == "EZE"
    assert vuelo.destino == "CUN"
    assert vuelo.precio_total is not None
    assert vuelo.aerolineas
    assert vuelo.escalas == 0
    assert vuelo.duracion_minutos is not None


def test_a_opcion_vuelo_con_campos_faltantes_no_rompe() -> None:
    vuelo = mod._a_opcion_vuelo({})

    assert vuelo.proveedor == "booking"
    assert vuelo.precio_total is None
    assert vuelo.aerolineas == []
    assert vuelo.escalas == 0


def test_elegir_candidato_hotel_prioriza_ciudad_sobre_otros_tipos() -> None:
    body = _cargar_fixture("booking_searchDestination_barcelona.json")

    elegido = mod._elegir_candidato(body["data"], "search_type", mod.ORDEN_TIPO_HOTEL)

    assert elegido["search_type"] == "city"
    assert elegido["name"] == "Barcelona"


def test_elegir_candidato_vuelo_usa_unico_resultado_si_no_hay_city() -> None:
    body = _cargar_fixture("booking_flights_searchDestination_cancun.json")

    elegido = mod._elegir_candidato(body["data"], "type", mod.ORDEN_TIPO_VUELO)

    assert elegido["type"] == "AIRPORT"
    assert elegido["code"] == "CUN"


def test_elegir_candidato_sin_resultados_lanza_error() -> None:
    with pytest.raises(client.ErrorRapidAPI):
        mod._elegir_candidato([], "search_type", mod.ORDEN_TIPO_HOTEL)


def test_verificar_envelope_lanza_si_status_false() -> None:
    with pytest.raises(client.ErrorRapidAPI):
        mod._verificar_envelope({"status": False, "message": "parametros invalidos"})


def test_verificar_envelope_devuelve_body_si_status_true() -> None:
    body = {"status": True, "data": []}

    assert mod._verificar_envelope(body) is body


def test_resolver_destino_hotel_usa_cache_si_hay_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    cacheado = DestinoResuelto(
        proveedor="booking_hoteles", texto_consultado="Barcelona", id_externo="-372490", tipo="city", nombre="Barcelona"
    )
    monkeypatch.setattr(mod, "buscar_destino_cacheado", lambda *_, **__: cacheado)
    llamado = MagicMock(side_effect=AssertionError("no deberia llamar a la red si hay cache"))
    monkeypatch.setattr(client, "llamar", llamado)

    resultado = mod.resolver_destino_hotel(MagicMock(), "Barcelona")

    assert resultado is cacheado
    llamado.assert_not_called()


def test_resolver_destino_hotel_sin_cache_llama_y_guarda(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _cargar_fixture("booking_searchDestination_barcelona.json")
    monkeypatch.setattr(mod, "buscar_destino_cacheado", lambda *_, **__: None)
    guardado = MagicMock()
    monkeypatch.setattr(mod, "guardar_destino_cacheado", guardado)
    monkeypatch.setattr(client, "llamar", lambda *_, **__: body)

    resultado = mod.resolver_destino_hotel(MagicMock(), "Barcelona")

    assert resultado.id_externo == "-372490"
    assert resultado.tipo == "city"
    guardado.assert_called_once()


def test_buscar_alojamiento_sirve_fixture_si_rapidapi_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    resuelto = DestinoResuelto(
        proveedor="booking_hoteles", texto_consultado="Barcelona", id_externo="-372490", tipo="city", nombre="Barcelona"
    )
    monkeypatch.setattr(mod, "resolver_destino_hotel", lambda *_, **__: resuelto)
    monkeypatch.setattr(client, "llamar", MagicMock(side_effect=client.ErrorCuotaAgotada("sin cuota")))

    from datetime import date

    resultados = mod.buscar_alojamiento(MagicMock(), "Barcelona", date(2026, 10, 15), date(2026, 10, 18))

    assert resultados
    assert all(alojamiento.es_fixture for alojamiento in resultados)
