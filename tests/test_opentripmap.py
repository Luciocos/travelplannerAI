"""Tests del cliente de OpenTripMap. Mockea httpx, no toca la red ni
consume cuota (ver ci-y-git.md, ningun test toca la red)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from asistente_viajes.ingesta import opentripmap


def test_buscar_por_radio_devuelve_la_lista(monkeypatch: pytest.MonkeyPatch) -> None:
    lista_esperada = [{"xid": "N1", "name": "Lugar 1", "kinds": "museums"}]

    def get_falso(url, params, timeout):
        return httpx.Response(200, json=lista_esperada, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    resultado = opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000)

    assert resultado == lista_esperada


def test_buscar_por_radio_propaga_error_como_error_opentripmap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_falso(url, params, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000)


def test_ingerir_destino_usa_cache_si_la_api_esta_caida(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directorio_raw = tmp_path / "raw"
    directorio_raw.mkdir()
    ruta_lista = directorio_raw / "salta_lista.json"
    ruta_lista.write_text(json.dumps([{"xid": "N1", "name": "Lugar 1"}]), encoding="utf-8")
    ruta_detalles = directorio_raw / "salta_detalles.json"
    ruta_detalles.write_text(
        json.dumps([{"xid": "N1", "name": "Lugar 1 detallado"}]), encoding="utf-8"
    )

    def buscar_falso(*args, **kwargs):
        raise opentripmap.ErrorOpenTripMap("caida simulada")

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    resultado = opentripmap.ingerir_destino(
        "Salta",
        lat=-24.79,
        lon=-65.41,
        radio_metros=5000,
        api_key="clave",
        directorio_raw=directorio_raw,
    )

    assert resultado == [{"xid": "N1", "name": "Lugar 1 detallado"}]


def test_ingerir_destino_relanza_si_no_hay_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directorio_raw = tmp_path / "raw"

    def buscar_falso(*args, **kwargs):
        raise opentripmap.ErrorOpenTripMap("caida simulada")

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.ingerir_destino(
            "Salta",
            lat=-24.79,
            lon=-65.41,
            radio_metros=5000,
            api_key="clave",
            directorio_raw=directorio_raw,
        )
