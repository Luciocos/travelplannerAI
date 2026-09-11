"""Tests de normalizar() (texto.py). No toca la red."""

from __future__ import annotations

from asistente_viajes.texto import normalizar


def test_normalizar_saca_tildes() -> None:
    assert normalizar("Cancún") == "cancun"


def test_normalizar_pone_minuscula() -> None:
    assert normalizar("CANCUN") == "cancun"


def test_normalizar_hace_trim() -> None:
    assert normalizar("  Cancun  ") == "cancun"
