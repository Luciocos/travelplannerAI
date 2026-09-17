"""Tests de preguntas.py: pregunta consolidada y sugerencias, 100%
deterministico, sin LLM."""

from __future__ import annotations

from asistente_viajes.preguntas import (
    armar_pregunta_consolidada,
    destinos_piloto_destacados,
    tipo_destino_de,
    valores_sugeridos,
)


def test_pregunta_consolidada_con_estado_vacio_menciona_todo_lo_que_falta() -> None:
    faltantes = [
        "destino",
        "tipo_destino",
        "intereses",
        "presupuesto",
        "fecha_inicio",
        "fecha_fin",
        "cantidad_personas",
    ]
    pregunta = armar_pregunta_consolidada(faltantes)

    assert "Barcelona" in pregunta
    assert "Miami" in pregunta
    assert "Cancun" in pregunta
    assert "historia" in pregunta
    assert "bajo, medio, alto" in pregunta
    assert "cuántas personas" in pregunta.lower()
    assert "para cuándo" in pregunta.lower()
    assert "usar sugerencias" in pregunta


def test_pregunta_consolidada_no_pregunta_tipo_destino_nunca() -> None:
    """tipo_destino se deriva del destino (D-14), nunca se pregunta aparte."""
    pregunta = armar_pregunta_consolidada(["tipo_destino", "presupuesto"])
    assert "tipo de destino" not in pregunta.lower()
    assert "montaña" not in pregunta.lower()


def test_pregunta_consolidada_fecha_inicio_y_fin_cuentan_como_un_solo_campo() -> None:
    pregunta = armar_pregunta_consolidada(["fecha_inicio", "fecha_fin"])
    assert pregunta.count("¿") == 1


def test_pregunta_consolidada_sin_faltantes_es_vacia() -> None:
    assert armar_pregunta_consolidada([]) == ""


def test_pregunta_consolidada_no_inventa_opciones_de_fecha() -> None:
    """P-08: antes se preguntaba '¿primera o segunda quincena de este
    mes?' sin que el usuario hubiera dicho nada de fechas."""
    pregunta = armar_pregunta_consolidada(["fecha_inicio", "fecha_fin"])
    assert "quincena" not in pregunta.lower()
    assert "este mes" not in pregunta.lower()


def test_valores_sugeridos_solo_para_los_campos_que_faltan() -> None:
    sugeridos = valores_sugeridos(["presupuesto"])
    assert sugeridos == {"presupuesto": "medio"}


def test_valores_sugeridos_nunca_sugiere_destino() -> None:
    sugeridos = valores_sugeridos(["destino", "presupuesto"])
    assert "destino" not in sugeridos


def test_valores_sugeridos_cuando_sugiere_duracion_dias() -> None:
    sugeridos = valores_sugeridos(["fecha_inicio", "fecha_fin"])
    assert sugeridos["duracion_dias"] == 5


def test_destinos_piloto_destacados_lista_los_tres() -> None:
    texto = destinos_piloto_destacados()
    assert "Barcelona" in texto
    assert "Miami" in texto
    assert "Cancun" in texto


def test_tipo_destino_de_deriva_del_destino_piloto() -> None:
    assert tipo_destino_de("Cancun") == "playa"
    assert tipo_destino_de("Barcelona") == "ciudad"


def test_tipo_destino_de_destino_no_piloto_es_none() -> None:
    assert tipo_destino_de("Tokio") is None


def test_tipo_destino_de_sin_destino_es_none() -> None:
    assert tipo_destino_de(None) is None


def test_tipo_destino_de_insensible_a_tildes() -> None:
    assert tipo_destino_de("Cancún") == "playa"
