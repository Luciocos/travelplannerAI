"""Tests del cliente HTTP compartido de RapidAPI (client.py). Mockea httpx,
la configuracion y la conexion a Postgres del contador de cuota. No toca
la red ni una base real."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from asistente_viajes.services.rapidapi import client as mod

RUTA_FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "asistente_viajes"
    / "services"
    / "rapidapi"
    / "fixtures"
)


def _configuracion_falsa(**overrides):
    base = {
        "usar_fixtures": False,
        "rapidapi_key": "clave-de-prueba",
        "rapidapi_quota_booking": 100,
        "rapidapi_quota_fly_scraper": 100,
    }
    base.update(overrides)
    configuracion = MagicMock()
    for nombre, valor in base.items():
        setattr(configuracion, nombre, valor)
    return configuracion


def _conexion_con_contador(cantidad_usada: int) -> MagicMock:
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (cantidad_usada,)
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_llamar_usa_fixture_si_use_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod, "cargar_configuracion", lambda: _configuracion_falsa(usar_fixtures=True)
    )
    datos_falsos = {"status": True, "data": []}
    monkeypatch.setattr(mod, "leer_fixture", lambda *_: datos_falsos)

    resultado = mod.llamar(
        MagicMock(), "booking", "booking-com15.p.rapidapi.com", "api/v1/hotels/searchHotels", {}
    )

    assert resultado is datos_falsos


def test_llamar_sirve_fixture_si_cuota_al_100_por_ciento(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod, "cargar_configuracion", lambda: _configuracion_falsa(rapidapi_quota_booking=10)
    )
    monkeypatch.setattr(mod, "leer_fixture", lambda *_: {"status": True, "data": []})
    llamado_http = MagicMock(
        side_effect=AssertionError("no deberia salir a la red con cuota agotada")
    )
    monkeypatch.setattr(httpx, "get", llamado_http)

    conexion = _conexion_con_contador(10)
    mod.llamar(conexion, "booking", "host", "endpoint", {})

    llamado_http.assert_not_called()


def test_llamar_reintenta_en_429_y_levanta_error_cuota_agotada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "cargar_configuracion", lambda: _configuracion_falsa())
    monkeypatch.setattr(mod, "_dormir", lambda _: None)
    monkeypatch.setattr(mod, "_incrementar_contador", lambda *_: None)

    llamadas = []

    def get_falso(url, headers, params, timeout):
        llamadas.append(1)
        return httpx.Response(
            429, json={"message": "quota exceeded"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(mod.ErrorCuotaAgotada):
        mod.llamar(_conexion_con_contador(0), "booking", "host", "endpoint", {})

    assert len(llamadas) == mod.MAXIMO_REINTENTOS + 1


def test_llamar_no_reintenta_error_4xx_no_reintentable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "cargar_configuracion", lambda: _configuracion_falsa())
    monkeypatch.setattr(mod, "_incrementar_contador", lambda *_: None)

    llamadas = []

    def get_falso(url, headers, params, timeout):
        llamadas.append(1)
        return httpx.Response(
            400, json={"message": "bad request"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(mod.ErrorRapidAPI):
        mod.llamar(_conexion_con_contador(0), "booking", "host", "endpoint", {})

    assert len(llamadas) == 1


def test_llamar_error_de_red_levanta_error_rapidapi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "cargar_configuracion", lambda: _configuracion_falsa())

    def get_falso(url, headers, params, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(mod.ErrorRapidAPI):
        mod.llamar(_conexion_con_contador(0), "booking", "host", "endpoint", {})


def test_llamar_devuelve_json_en_respuesta_exitosa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "cargar_configuracion", lambda: _configuracion_falsa())
    monkeypatch.setattr(mod, "_incrementar_contador", lambda *_: None)

    def get_falso(url, headers, params, timeout):
        return httpx.Response(
            200, json={"status": True, "data": []}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", get_falso)

    resultado = mod.llamar(_conexion_con_contador(0), "booking", "host", "endpoint", {})

    assert resultado == {"status": True, "data": []}


def test_leer_fixture_existente_devuelve_contenido() -> None:
    resultado = mod.leer_fixture("booking", "api/v1/hotels/searchHotels")

    assert resultado["status"] is True


def test_leer_fixture_inexistente_lanza_error_rapidapi() -> None:
    with pytest.raises(mod.ErrorRapidAPI):
        mod.leer_fixture("booking", "endpoint/que/no/existe")


def test_guardar_fixture_escribe_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "RUTA_FIXTURES", tmp_path)

    ruta = mod.guardar_fixture("booking", "api/v1/test", {"status": True})

    assert ruta.exists()
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"status": True}
