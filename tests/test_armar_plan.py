"""Tests de armar_plan (RF5, nucleo). Mockea buscar_atractivos y la
conexion, no toca la red ni Postgres real."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.tools import armar_plan as mod


def _resultado(
    nombre: str,
    categoria: str = "museums",
    rango_precio: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    id_: int | None = None,
) -> ResultadoRecuperado:
    return ResultadoRecuperado(
        id=id_,
        nombre=nombre,
        categoria=categoria,
        texto="texto real de sobra",
        rango_precio=rango_precio,
        lat=lat,
        lon=lon,
    )


def test_cantidad_dias_con_fechas_exactas_inclusive() -> None:
    estado = PreferenciasViaje(fecha_inicio=date(2026, 10, 15), fecha_fin=date(2026, 10, 17))
    assert mod._cantidad_dias(estado) == 3


def test_cantidad_dias_mismo_dia_es_uno() -> None:
    estado = PreferenciasViaje(fecha_inicio=date(2026, 10, 15), fecha_fin=date(2026, 10, 15))
    assert mod._cantidad_dias(estado) == 1


def test_cantidad_dias_usa_duracion_dias_sin_fechas() -> None:
    """D-14: un plan puede armarse con 'X dias, fecha a confirmar'."""
    estado = PreferenciasViaje(duracion_dias=7)
    assert mod._cantidad_dias(estado) == 7


def test_cantidad_dias_sin_fechas_ni_duracion_levanta_error_claro() -> None:
    estado = PreferenciasViaje()
    with pytest.raises(mod.ErrorFechasIncompletas):
        mod._cantidad_dias(estado)


def test_repartir_por_dia_no_repite_actividades() -> None:
    candidatos = [_resultado(f"Lugar {i}") for i in range(6)]

    grupos = mod._repartir_por_dia(candidatos, dias_totales=2)

    nombres_usados = [c.nombre for grupo in grupos for c in grupo]
    assert len(nombres_usados) == len(set(nombres_usados))
    assert len(grupos) == 2
    for grupo in grupos:
        assert mod.ACTIVIDADES_POR_DIA_MIN <= len(grupo) <= mod.ACTIVIDADES_POR_DIA_MAX


def test_repartir_por_dia_agrupa_por_cercania_geografica() -> None:
    """Dos clusters bien separados (uno cerca de (0,0), otro cerca de
    (10,10)) tienen que quedar cada uno en un solo dia, no mezclados."""
    cluster_a = [_resultado(f"A{i}", lat=0.0 + i * 0.01, lon=0.0 + i * 0.01) for i in range(3)]
    cluster_b = [_resultado(f"B{i}", lat=10.0 + i * 0.01, lon=10.0 + i * 0.01) for i in range(3)]

    grupos = mod._repartir_por_dia(cluster_a + cluster_b, dias_totales=2)

    nombres_dia_1 = {c.nombre for c in grupos[0]}
    nombres_dia_2 = {c.nombre for c in grupos[1]}
    assert nombres_dia_1 in ({"A0", "A1", "A2"}, {"B0", "B1", "B2"})
    assert nombres_dia_2 in ({"A0", "A1", "A2"}, {"B0", "B1", "B2"})
    assert nombres_dia_1 != nombres_dia_2


def test_armar_dias_con_pocos_candidatos_no_deja_dias_vacios() -> None:
    candidatos = [_resultado("Unico lugar")]

    dias = mod._armar_dias(candidatos, dias_totales=3, fecha_inicio=None, gasto_diario=0.0)

    assert len(dias) == 3
    for dia in dias:
        assert len(dia.actividades) >= 1
    nombres = [a.nombre for dia in dias for a in dia.actividades]
    assert mod.NOMBRE_DIA_LIBRE in nombres


def test_armar_dias_asigna_fecha_de_calendario_por_dia() -> None:
    candidatos = [_resultado(f"Lugar {i}") for i in range(4)]

    dias = mod._armar_dias(
        candidatos, dias_totales=2, fecha_inicio=date(2027, 1, 10), gasto_diario=0.0
    )

    assert dias[0].fecha == date(2027, 1, 10)
    assert dias[1].fecha == date(2027, 1, 11)


def test_armar_dias_sin_fecha_de_inicio_deja_fecha_none() -> None:
    dias = mod._armar_dias(
        [_resultado("Lugar")], dias_totales=1, fecha_inicio=None, gasto_diario=0.0
    )
    assert dias[0].fecha is None


def test_armar_plan_calcula_costo_total_y_por_grupo(monkeypatch) -> None:
    candidatos = [_resultado("Museo", "museums"), _resultado("Ruinas", "historic")]
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: candidatos)

    estado = PreferenciasViaje(
        destino="Cancun",
        intereses=["historia"],
        presupuesto="medio",
        fecha_inicio=date(2026, 10, 15),
        fecha_fin=date(2026, 10, 15),
        cantidad_personas=2,
    )

    plan = mod.armar_plan(MagicMock(), estado)

    assert plan.destino == "Cancun"
    assert plan.moneda == "USD"
    assert len(plan.dias) == 1
    # museums(10) + historic(5) = 15 de actividades, + gasto diario Cancun/medio (45) = 60
    assert plan.costo_actividades_total == 15.0
    assert plan.gasto_estimado_total == 45.0
    assert plan.costo_total_estimado == 60.0
    assert plan.costo_total_grupo == 120.0
    assert plan.supuestos == []


def test_armar_plan_rango_precio_manda_sobre_categoria(monkeypatch) -> None:
    candidatos = [_resultado("Restaurante curado", "foods", rango_precio="$$")]
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: candidatos)

    estado = PreferenciasViaje(
        destino="Cancun",
        presupuesto="bajo",
        fecha_inicio=date(2026, 10, 15),
        fecha_fin=date(2026, 10, 15),
        cantidad_personas=1,
    )

    plan = mod.armar_plan(MagicMock(), estado)

    assert plan.costo_actividades_total == 25.0  # $$ -> 25, no el costo base de "foods" (15)


def test_armar_plan_sin_presupuesto_marca_el_supuesto(monkeypatch) -> None:
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: [])

    estado = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2026, 10, 15), fecha_fin=date(2026, 10, 15)
    )

    plan = mod.armar_plan(MagicMock(), estado)

    assert "presupuesto no indicado, se uso un gasto diario de referencia" in plan.supuestos
    assert plan.cantidad_personas == 1


def test_armar_plan_con_duracion_dias_marca_el_supuesto_de_fecha(monkeypatch) -> None:
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: [])

    estado = PreferenciasViaje(destino="Cancun", presupuesto="medio", duracion_dias=3)

    plan = mod.armar_plan(MagicMock(), estado)

    assert len(plan.dias) == 3
    assert all(dia.fecha is None for dia in plan.dias)
    assert "sin fecha de inicio confirmada, el plan es por cantidad de dias" in plan.supuestos


def test_armar_plan_sin_fechas_ni_duracion_levanta_error_fechas_incompletas() -> None:
    estado = PreferenciasViaje(destino="Cancun")
    with pytest.raises(mod.ErrorFechasIncompletas):
        mod.armar_plan(MagicMock(), estado)


def _conexion_con_returning(itinerario_id: int) -> MagicMock:
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (itinerario_id,)
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_guardar_itinerario_inserta_cabecera_y_items_con_documento_id() -> None:
    conexion = _conexion_con_returning(itinerario_id=42)
    plan = mod.PlanDeViaje(
        destino="Cancun",
        dias=[
            mod.DiaDelPlan(
                dia=1,
                actividades=[
                    mod.ActividadDelPlan(
                        documento_id=7, nombre="Museo", categoria="museums", costo_estimado=10.0
                    )
                ],
                costo_actividades=10.0,
                gasto_estimado_dia=0.0,
                costo_dia=10.0,
            )
        ],
        costo_actividades_total=10.0,
        gasto_estimado_total=0.0,
        costo_total_estimado=10.0,
        cantidad_personas=2,
        costo_total_grupo=20.0,
    )
    estado = PreferenciasViaje(
        destino="Cancun",
        fecha_inicio=date(2026, 10, 15),
        fecha_fin=date(2026, 10, 15),
        presupuesto="medio",
    )

    itinerario_id = mod.guardar_itinerario(conexion, estado, plan)

    assert itinerario_id == 42
    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    assert cursor_usado.execute.call_count == 2  # 1 itinerario + 1 item
    parametros_item = cursor_usado.execute.call_args.args[1]
    assert parametros_item["documento_id"] == 7


def test_tool_armar_plan_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod.crear_tool_armar_plan(conexion=MagicMock())

    assert tool_creada.name == "armar_plan"
    assert tool_creada.description
    assert tool_creada.args_schema is mod.ArgsArmarPlan


def test_resumen_markdown_incluye_dias_y_costo_total() -> None:
    plan = mod.PlanDeViaje(
        destino="Cancun",
        dias=[
            mod.DiaDelPlan(
                dia=1,
                actividades=[
                    mod.ActividadDelPlan(
                        nombre="Museo Maya", categoria="museums", costo_estimado=10.0
                    )
                ],
                costo_actividades=10.0,
                gasto_estimado_dia=45.0,
                costo_dia=55.0,
            )
        ],
        costo_actividades_total=10.0,
        gasto_estimado_total=45.0,
        costo_total_estimado=55.0,
        cantidad_personas=2,
        costo_total_grupo=110.0,
        supuestos=["presupuesto no indicado, se uso un gasto diario de referencia"],
    )

    markdown = mod.resumen_markdown(plan)

    assert "Cancun" in markdown
    assert "Museo Maya" in markdown
    assert "110" in markdown
    assert "presupuesto no indicado" in markdown
