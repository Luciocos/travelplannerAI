"""Tests de info_destino (RF8). Mockea httpx y usa un paises.json temporal,
no toca la red."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest

from asistente_viajes.tools import info_destino as mod


def test_obtener_clima_devuelve_pronostico_dentro_del_horizonte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datos_falsos = {
        "daily": {
            "temperature_2m_max": [30.0, 31.0],
            "temperature_2m_min": [22.0, 23.0],
            "precipitation_sum": [0.0, 2.0],
        }
    }

    def get_falso(url, params, timeout):
        return httpx.Response(200, json=datos_falsos, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    hoy = date(2026, 9, 10)
    clima = mod.obtener_clima(
        lat=25.76,
        lon=-80.19,
        fecha_inicio=hoy + timedelta(days=2),
        fecha_fin=hoy + timedelta(days=3),
        hoy=hoy,
    )

    assert clima.disponible
    assert clima.temperatura_maxima == [30.0, 31.0]


def test_obtener_clima_fuera_de_horizonte_no_inventa_dato() -> None:
    hoy = date(2026, 9, 10)
    clima = mod.obtener_clima(
        lat=25.76,
        lon=-80.19,
        fecha_inicio=hoy + timedelta(days=200),
        fecha_fin=hoy + timedelta(days=207),
        hoy=hoy,
    )

    assert not clima.disponible
    assert "16 dias" in clima.detalle or "16" in clima.detalle


def test_obtener_clima_api_caida_no_rompe(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, params, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    hoy = date(2026, 9, 10)
    clima = mod.obtener_clima(
        lat=0,
        lon=0,
        fecha_inicio=hoy + timedelta(days=1),
        fecha_fin=hoy + timedelta(days=2),
        hoy=hoy,
    )

    assert not clima.disponible


def test_obtener_idioma_moneda_lee_la_tabla_de_referencia(tmp_path: Path) -> None:
    ruta = tmp_path / "paises.json"
    ruta.write_text(json.dumps({"Miami": {"idioma": "ingles", "moneda": "USD"}}), encoding="utf-8")

    resultado = mod.obtener_idioma_moneda("Miami", ruta_paises=ruta)

    assert resultado.idioma == "ingles"
    assert resultado.moneda == "USD"


def test_obtener_idioma_moneda_pais_desconocido_no_rompe(tmp_path: Path) -> None:
    ruta = tmp_path / "paises.json"
    ruta.write_text(json.dumps({}), encoding="utf-8")

    resultado = mod.obtener_idioma_moneda("Narnia", ruta_paises=ruta)

    assert resultado.idioma is None
    assert resultado.moneda is None
