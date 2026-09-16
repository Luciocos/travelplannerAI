"""Tests de la tabla de costos (costos.py). Logica pura, sin red ni DB."""

from __future__ import annotations

from asistente_viajes.costos import (
    COSTO_BASE_POR_CATEGORIA,
    COSTO_POR_DEFECTO,
    GASTO_DIARIO_POR_DEFECTO,
    estimar_costo,
    estimar_gasto_diario,
)


def test_estimar_costo_usa_rango_precio_si_esta_presente() -> None:
    assert estimar_costo(categoria="museums", rango_precio="$$") == 25.0


def test_estimar_costo_usa_categoria_primaria_si_no_hay_rango_precio() -> None:
    assert estimar_costo(categoria="historic,archaeology", rango_precio=None) == 5.0
    assert estimar_costo(categoria="architecture", rango_precio=None) == 0.0


def test_estimar_costo_categoria_desconocida_usa_default() -> None:
    assert estimar_costo(categoria="categoria_rara", rango_precio=None) == COSTO_POR_DEFECTO


def test_estimar_costo_sin_nada_usa_default() -> None:
    assert estimar_costo(categoria=None, rango_precio=None) == COSTO_POR_DEFECTO


def test_estimar_costo_rango_precio_invalido_cae_a_categoria() -> None:
    assert (
        estimar_costo(categoria="museums", rango_precio="???")
        == COSTO_BASE_POR_CATEGORIA["museums"]
    )


def test_estimar_gasto_diario_por_destino_y_presupuesto() -> None:
    assert estimar_gasto_diario("Cancun", "bajo") == 25.0
    assert estimar_gasto_diario("Miami", "alto") == 130.0


def test_estimar_gasto_diario_destino_no_piloto_usa_default() -> None:
    assert estimar_gasto_diario("Narnia", "medio") == GASTO_DIARIO_POR_DEFECTO


def test_estimar_gasto_diario_sin_presupuesto_usa_default() -> None:
    assert estimar_gasto_diario("Cancun", None) == GASTO_DIARIO_POR_DEFECTO
