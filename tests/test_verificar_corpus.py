"""Tests de scripts/verificar_corpus.py. No toca Postgres real: mockea
obtener_conexion y los destinos piloto."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from scripts import verificar_corpus as mod


@contextmanager
def _conexion_con_filas(filas: list[tuple]):
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = filas
    conexion.cursor.return_value.__enter__.return_value = cursor
    yield conexion


def test_todos_los_destinos_por_encima_del_minimo(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Cancun": {}, "Miami": {}})
    filas = [
        ("Cancun", "atractivos", "curado", 20),
        ("Miami", "atractivos", "opentripmap", 35),
    ]
    monkeypatch.setattr(mod, "obtener_conexion", lambda: _conexion_con_filas(filas))

    assert mod.main() == 0


def test_destino_por_debajo_del_minimo_devuelve_error(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Cancun": {}})
    filas = [("Cancun", "atractivos", "curado", 13)]
    monkeypatch.setattr(mod, "obtener_conexion", lambda: _conexion_con_filas(filas))

    assert mod.main() == 1


def test_destino_sin_ninguna_fila_cuenta_como_cero(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Barcelona": {}})
    monkeypatch.setattr(mod, "obtener_conexion", lambda: _conexion_con_filas([]))

    assert mod.main() == 1
