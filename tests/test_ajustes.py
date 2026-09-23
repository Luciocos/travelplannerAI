"""Tests de ajustes.py (Fase 7E, D-22). No toca la red ni Postgres."""

from __future__ import annotations

from asistente_viajes.ajustes import (
    AjustePlan,
    actividades_por_dia,
    ajustes_no_aplicables,
    describir,
    dias_fuera_de_rango,
    dias_libres,
    excluye,
    resolver_dia,
)


def _ajuste(**kwargs) -> AjustePlan:
    base = {"tipo": "dia_libre"}
    base.update(kwargs)
    return AjustePlan(**base)


# --- resolver_dia -----------------------------------------------------


def test_resolver_dia_none_es_el_ultimo_dia() -> None:
    assert resolver_dia(None, dias_totales=5) == 5


def test_resolver_dia_positivo_dentro_de_rango_se_devuelve_igual() -> None:
    assert resolver_dia(2, dias_totales=5) == 2


def test_resolver_dia_negativo_cuenta_desde_el_final() -> None:
    assert resolver_dia(-1, dias_totales=5) == 5
    assert resolver_dia(-2, dias_totales=5) == 4


def test_resolver_dia_positivo_fuera_de_rango_devuelve_none() -> None:
    assert resolver_dia(8, dias_totales=5) is None


def test_resolver_dia_negativo_fuera_de_rango_devuelve_none() -> None:
    assert resolver_dia(-6, dias_totales=5) is None


def test_resolver_dia_sin_plan_devuelve_none() -> None:
    assert resolver_dia(1, dias_totales=0) is None
    assert resolver_dia(None, dias_totales=0) is None


# --- dias_libres --------------------------------------------------------


def test_dias_libres_resuelve_los_indices_pedidos() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(dia=-1)]

    assert dias_libres(ajustes, dias_totales=5) == {1, 5}


def test_dias_libres_ignora_ajustes_de_otro_tipo() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(tipo="excluir", valor="museos")]

    assert dias_libres(ajustes, dias_totales=5) == {1}


def test_dias_libres_nunca_deja_el_plan_entero_libre() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(dia=2), _ajuste(dia=3)]

    assert dias_libres(ajustes, dias_totales=3) == set()


def test_dias_libres_ignora_dias_fuera_de_rango() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(dia=9)]

    assert dias_libres(ajustes, dias_totales=5) == {1}


# --- dias_fuera_de_rango --------------------------------------------------


def test_dias_fuera_de_rango_detecta_el_dia_inexistente() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(dia=9)]

    resultado = dias_fuera_de_rango(ajustes, dias_totales=5)

    assert [a.dia for a in resultado] == [9]


def test_dias_fuera_de_rango_ignora_ajustes_de_otro_tipo() -> None:
    ajustes = [_ajuste(tipo="excluir", valor="museos")]

    assert dias_fuera_de_rango(ajustes, dias_totales=5) == []


def test_dias_fuera_de_rango_vacio_si_todos_resuelven() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(dia=-1)]

    assert dias_fuera_de_rango(ajustes, dias_totales=5) == []


# --- excluye --------------------------------------------------------------


def test_excluye_matchea_por_nombre() -> None:
    ajustes = [_ajuste(tipo="excluir", valor="Tivoli")]

    assert excluye(ajustes, nombre="Teatre Tivoli", categoria=None) is True


def test_excluye_matchea_por_categoria() -> None:
    ajustes = [_ajuste(tipo="excluir", valor="museum")]

    assert excluye(ajustes, nombre="algo", categoria="museums") is True


def test_excluye_traduce_la_categoria_del_cliente_al_kind_en_ingles() -> None:
    """El cliente pide en español ("sacame los teatros") pero `categoria` es
    el kind crudo de OpenTripMap, en inglés. Con match por substring literal
    eso no cruzaba nunca, asi que una exclusion por categoria simplemente no
    funcionaba: bug real encontrado escribiendo estos tests. `excluye` usa
    una tabla de equivalencias para cerrar esa brecha."""
    ajustes = [_ajuste(tipo="excluir", valor="teatros")]

    assert excluye(ajustes, nombre="Teatre Tivoli", categoria="theatres_and_entertainments") is True


def test_excluye_traduce_tambien_en_singular_y_para_otras_categorias() -> None:
    assert excluye([_ajuste(tipo="excluir", valor="museo")], nombre="X", categoria="museums")
    assert excluye([_ajuste(tipo="excluir", valor="iglesias")], nombre="X", categoria="churches")
    assert excluye([_ajuste(tipo="excluir", valor="parques")], nombre="X", categoria="gardens_and_parks")


def test_excluye_una_categoria_no_arrastra_a_las_demas() -> None:
    """La traduccion no puede volverse un cajon de sastre: pedir sacar los
    teatros no tiene que sacar tambien los parques."""
    ajustes = [_ajuste(tipo="excluir", valor="teatros")]

    assert excluye(ajustes, nombre="Parque Güell", categoria="gardens_and_parks") is False


def test_excluye_ignora_tildes_y_mayusculas() -> None:
    ajustes = [_ajuste(tipo="excluir", valor="MUSEO")]

    assert excluye(ajustes, nombre="Muséo de Arte", categoria=None) is True


def test_excluye_devuelve_false_sin_match() -> None:
    ajustes = [_ajuste(tipo="excluir", valor="teatro")]

    assert excluye(ajustes, nombre="Museo del Prado", categoria="museums") is False


def test_excluye_ignora_ajustes_de_otro_tipo() -> None:
    ajustes = [_ajuste(dia=1)]

    assert excluye(ajustes, nombre="Teatro Colon", categoria=None) is False


def test_excluye_ignora_ajustes_sin_valor() -> None:
    ajustes = [_ajuste(tipo="excluir", valor=None)]

    assert excluye(ajustes, nombre="Teatro Colon", categoria=None) is False


# --- actividades_por_dia ---------------------------------------------------


def test_actividades_por_dia_usa_el_default_sin_ajustes() -> None:
    assert actividades_por_dia([], por_defecto=3) == 3


def test_actividades_por_dia_acota_el_maximo() -> None:
    ajustes = [_ajuste(tipo="actividades_por_dia", cantidad=10)]

    assert actividades_por_dia(ajustes, por_defecto=3) == 6


def test_actividades_por_dia_acota_el_minimo() -> None:
    ajustes = [_ajuste(tipo="actividades_por_dia", cantidad=0)]

    # cantidad=0 es falsy, asi que el ajuste no pisa el default (ver
    # implementacion: `if ajuste.tipo == ... and ajuste.cantidad`).
    assert actividades_por_dia(ajustes, por_defecto=3) == 3


def test_actividades_por_dia_negativa_se_acota_a_uno() -> None:
    ajustes = [_ajuste(tipo="actividades_por_dia", cantidad=-2)]

    assert actividades_por_dia(ajustes, por_defecto=3) == 1


def test_actividades_por_dia_gana_el_ultimo_ajuste() -> None:
    ajustes = [
        _ajuste(tipo="actividades_por_dia", cantidad=2),
        _ajuste(tipo="actividades_por_dia", cantidad=4),
    ]

    assert actividades_por_dia(ajustes, por_defecto=3) == 4


# --- ajustes_no_aplicables --------------------------------------------------


def test_ajustes_no_aplicables_filtra_solo_tipo_otro() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(tipo="otro", pedido_original="algo raro")]

    resultado = ajustes_no_aplicables(ajustes)

    assert len(resultado) == 1
    assert resultado[0].pedido_original == "algo raro"


def test_ajustes_no_aplicables_vacio_sin_tipo_otro() -> None:
    ajustes = [_ajuste(dia=1), _ajuste(tipo="excluir", valor="museos")]

    assert ajustes_no_aplicables(ajustes) == []


# --- describir --------------------------------------------------------------


def test_describir_dia_libre() -> None:
    ajuste = _ajuste(dia=-1)

    assert describir(ajuste, dias_totales=5) == "dia 5 sin actividades, a pedido suyo"


def test_describir_dia_libre_fuera_de_rango_es_vacio() -> None:
    ajuste = _ajuste(dia=9)

    assert describir(ajuste, dias_totales=5) == ""


def test_describir_excluir() -> None:
    ajuste = _ajuste(tipo="excluir", valor="teatros")

    assert describir(ajuste, dias_totales=5) == "se excluyo 'teatros' a pedido suyo"


def test_describir_excluir_sin_valor_es_vacio() -> None:
    ajuste = _ajuste(tipo="excluir", valor=None)

    assert describir(ajuste, dias_totales=5) == ""


def test_describir_actividades_por_dia() -> None:
    ajuste = _ajuste(tipo="actividades_por_dia", cantidad=4)

    assert describir(ajuste, dias_totales=5) == "4 actividades por dia, a pedido suyo"


def test_describir_actividades_por_dia_sin_cantidad_es_vacio() -> None:
    ajuste = _ajuste(tipo="actividades_por_dia", cantidad=None)

    assert describir(ajuste, dias_totales=5) == ""


def test_describir_otro_es_vacio() -> None:
    ajuste = _ajuste(tipo="otro", pedido_original="algo raro")

    assert describir(ajuste, dias_totales=5) == ""
