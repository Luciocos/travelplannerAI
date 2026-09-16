"""Tests de la consulta canonica de recuperacion. Mockea la conexion a
Postgres y el modelo de embeddings, no toca la red ni una base real."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from asistente_viajes.recuperacion import _consulta
from asistente_viajes.recuperacion.atractivos import buscar_atractivos
from asistente_viajes.recuperacion.comercios import buscar_comercios
from asistente_viajes.recuperacion.faq import buscar_faq


@pytest.fixture(autouse=True)
def _embeddings_falsos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_consulta, "embeber_texto", lambda texto: [0.1, 0.2, 0.3])


def _conexion_falsa(filas: list[tuple]) -> MagicMock:
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = filas
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_buscar_filtra_por_corpus_y_destino_y_devuelve_resultados() -> None:
    fila = (
        1,
        "Museo de Arqueologia",
        "museums",
        "texto largo sobre el museo",
        None,
        None,
        -24.7,
        -65.4,
    )
    conexion = _conexion_falsa([fila])

    resultados = _consulta.buscar(conexion, corpus="atractivos", destino="Salta", consulta="museos")

    assert len(resultados) == 1
    assert resultados[0].nombre == "Museo de Arqueologia"
    assert resultados[0].id == 1
    assert resultados[0].lat == -24.7
    assert resultados[0].lon == -65.4

    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    parametros_enviados = cursor_usado.execute.call_args.args[1]
    assert parametros_enviados["corpus"] == "atractivos"
    assert parametros_enviados["destino"] == "Salta"


def test_buscar_atractivos_arma_la_consulta_con_los_intereses() -> None:
    conexion = _conexion_falsa([])

    buscar_atractivos(conexion, destino="Salta", intereses=["historia", "caminatas"], k=3)

    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    parametros_enviados = cursor_usado.execute.call_args.args[1]
    assert parametros_enviados["k"] == 3


def test_buscar_comercios_usa_la_consulta_puntual() -> None:
    conexion = _conexion_falsa([])

    buscar_comercios(conexion, destino="Salta", consulta="donde comer barato")

    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    parametros_enviados = cursor_usado.execute.call_args.args[1]
    assert parametros_enviados["corpus"] == "comercios"


def test_buscar_faq_usa_la_consulta_puntual() -> None:
    conexion = _conexion_falsa([])

    buscar_faq(conexion, destino="Cancun", consulta="es seguro tomar un taxi")

    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    parametros_enviados = cursor_usado.execute.call_args.args[1]
    assert parametros_enviados["corpus"] == "faq"
