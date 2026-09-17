"""Tests de services/cambio.py (conversion de moneda, D-18). Mockea httpx,
no toca la red."""

from __future__ import annotations

import httpx
import pytest

from asistente_viajes.services import cambio as mod


@pytest.fixture(autouse=True)
def _sin_cache_entre_tests():
    mod._cache.clear()
    yield
    mod._cache.clear()


def test_convertir_a_ars_usa_dolarapi(monkeypatch: pytest.MonkeyPatch) -> None:
    datos = [
        {"casa": "oficial", "venta": 1500.0},
        {"casa": "tarjeta", "venta": 2000.0},
    ]

    def get_falso(url, timeout):
        return httpx.Response(200, json=datos, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    cotizacion = mod.convertir_desde_usd(100.0, "ars")

    assert cotizacion.disponible
    assert cotizacion.ars_oficial == 150000.0
    assert cotizacion.ars_tarjeta == 200000.0
    assert "dólar oficial" in cotizacion.detalle
    assert "dólar tarjeta" in cotizacion.detalle


def test_convertir_a_ars_sin_respuesta_no_rompe(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    cotizacion = mod.convertir_desde_usd(100.0, "ARS")

    assert not cotizacion.disponible
    assert "caida simulada" not in cotizacion.detalle


def test_convertir_a_otra_moneda_usa_exchange_rate_api(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, timeout):
        return httpx.Response(200, json={"rates": {"EUR": 0.9}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    cotizacion = mod.convertir_desde_usd(100.0, "EUR")

    assert cotizacion.disponible
    assert "EUR 90" in cotizacion.detalle
    assert "Rates By Exchange Rate API" in cotizacion.detalle


def test_convertir_a_moneda_no_disponible_no_inventa_tasa(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, timeout):
        return httpx.Response(200, json={"rates": {"EUR": 0.9}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    cotizacion = mod.convertir_desde_usd(100.0, "XYZ")

    assert not cotizacion.disponible
    assert "XYZ" in cotizacion.detalle


def test_segunda_llamada_usa_cache_no_pide_de_nuevo(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = []

    def get_falso(url, timeout):
        llamadas.append(url)
        return httpx.Response(
            200, json=[{"casa": "oficial", "venta": 1500.0}], request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", get_falso)

    mod.convertir_desde_usd(50.0, "ARS")
    mod.convertir_desde_usd(200.0, "ARS")

    assert len(llamadas) == 1
