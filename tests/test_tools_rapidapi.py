"""Tests de las tools buscar_alojamiento (RF6) y buscar_vuelos (RF7).
Mockea la funcion de services/rapidapi/booking.py, no toca la red ni
Postgres real."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from asistente_viajes.services.rapidapi.models import Alojamiento, OpcionVuelo
from asistente_viajes.tools import buscar_alojamiento as mod_alojamiento
from asistente_viajes.tools import buscar_vuelos as mod_vuelos


def test_tool_buscar_alojamiento_devuelve_dicts(monkeypatch) -> None:
    alojamiento = Alojamiento(nombre="H10 Casanova", proveedor="booking", precio_total=1089.0, moneda="USD")
    monkeypatch.setattr(mod_alojamiento, "_buscar_alojamiento", lambda *_, **__: [alojamiento])

    tool_creada = mod_alojamiento.crear_tool_buscar_alojamiento(conexion=MagicMock())
    resultado = tool_creada.invoke(
        {"destino": "Barcelona", "fecha_inicio": date(2026, 10, 15), "fecha_fin": date(2026, 10, 18)}
    )

    assert resultado == [alojamiento.model_dump()]


def test_tool_buscar_alojamiento_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_alojamiento.crear_tool_buscar_alojamiento(conexion=MagicMock())

    assert tool_creada.name == "buscar_alojamiento"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_alojamiento.ArgsBuscarAlojamiento


def test_tool_buscar_vuelos_devuelve_dicts(monkeypatch) -> None:
    vuelo = OpcionVuelo(proveedor="booking", origen="EZE", destino="CUN", precio_total=545.93, moneda="USD")
    monkeypatch.setattr(mod_vuelos, "_buscar_vuelos", lambda *_, **__: [vuelo])

    tool_creada = mod_vuelos.crear_tool_buscar_vuelos(conexion=MagicMock())
    resultado = tool_creada.invoke(
        {"origen": "Buenos Aires", "destino": "Cancun", "fecha_salida": date(2026, 10, 15)}
    )

    assert resultado == [vuelo.model_dump()]


def test_tool_buscar_vuelos_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_vuelos.crear_tool_buscar_vuelos(conexion=MagicMock())

    assert tool_creada.name == "buscar_vuelos"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_vuelos.ArgsBuscarVuelos
