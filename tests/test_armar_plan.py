"""Tests de armar_plan (RF5, nucleo). Mockea buscar_atractivos y la
conexion, no toca la red ni Postgres real."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.tools import armar_plan as mod


def _resultado(nombre: str, categoria: str = "museums") -> ResultadoRecuperado:
    return ResultadoRecuperado(nombre=nombre, categoria=categoria, texto="texto real de sobra")


def test_costo_actividad_usa_la_tabla_por_categoria() -> None:
    assert mod._costo_actividad("museums") == 10.0
    assert mod._costo_actividad("historic,archaeology") == 5.0
    assert mod._costo_actividad("architecture") == 0.0


def test_costo_actividad_categoria_desconocida_usa_default() -> None:
    assert mod._costo_actividad("categoria_rara") == mod.COSTO_BASE_DEFAULT


def test_costo_actividad_sin_categoria_usa_default() -> None:
    assert mod._costo_actividad(None) == mod.COSTO_BASE_DEFAULT


def test_cantidad_dias_inclusive() -> None:
    assert mod._cantidad_dias(date(2026, 10, 15), date(2026, 10, 17)) == 3


def test_cantidad_dias_mismo_dia_es_uno() -> None:
    assert mod._cantidad_dias(date(2026, 10, 15), date(2026, 10, 15)) == 1


def test_repartir_por_dia_no_repite_actividades() -> None:
    candidatos = [_resultado(f"Lugar {i}") for i in range(6)]

    dias = mod._repartir_por_dia(candidatos, dias_totales=2)

    nombres_usados = [a.nombre for dia in dias for a in dia.actividades]
    assert len(nombres_usados) == len(set(nombres_usados))
    assert len(dias) == 2
    for dia in dias:
        assert mod.ACTIVIDADES_POR_DIA_MIN <= len(dia.actividades) <= mod.ACTIVIDADES_POR_DIA_MAX


def test_repartir_por_dia_con_pocos_candidatos_no_rompe() -> None:
    candidatos = [_resultado("Unico lugar")]

    dias = mod._repartir_por_dia(candidatos, dias_totales=3)

    assert len(dias) == 3
    assert sum(len(dia.actividades) for dia in dias) == 1


def test_armar_plan_calcula_costo_total_y_por_grupo(monkeypatch) -> None:
    candidatos = [_resultado("Museo", "museums"), _resultado("Ruinas", "historic")]
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: candidatos)

    estado = PreferenciasViaje(
        destino="Cancun",
        intereses=["historia"],
        fecha_inicio=date(2026, 10, 15),
        fecha_fin=date(2026, 10, 15),
        cantidad_personas=2,
    )

    plan = mod.armar_plan(MagicMock(), estado)

    assert plan.destino == "Cancun"
    assert len(plan.dias) == 1
    assert plan.costo_total_estimado == 15.0
    assert plan.costo_total_grupo == 30.0


def test_armar_plan_sin_cantidad_personas_asume_uno(monkeypatch) -> None:
    monkeypatch.setattr(mod, "buscar_atractivos", lambda *_, **__: [])

    estado = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2026, 10, 15), fecha_fin=date(2026, 10, 15)
    )

    plan = mod.armar_plan(MagicMock(), estado)

    assert plan.cantidad_personas == 1


def _conexion_con_returning(itinerario_id: int) -> MagicMock:
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = (itinerario_id,)
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion


def test_guardar_itinerario_inserta_cabecera_y_items() -> None:
    conexion = _conexion_con_returning(itinerario_id=42)
    plan = mod.PlanDeViaje(
        destino="Cancun",
        dias=[
            mod.DiaDelPlan(
                dia=1,
                actividades=[mod.ActividadDelPlan(nombre="Museo", categoria="museums", costo_estimado=10.0)],
                costo_dia=10.0,
            )
        ],
        costo_total_estimado=10.0,
        cantidad_personas=2,
        costo_total_grupo=20.0,
    )
    estado = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2026, 10, 15), fecha_fin=date(2026, 10, 15), presupuesto="medio"
    )

    itinerario_id = mod.guardar_itinerario(conexion, estado, plan)

    assert itinerario_id == 42
    cursor_usado = conexion.cursor.return_value.__enter__.return_value
    assert cursor_usado.execute.call_count == 2  # 1 itinerario + 1 item


def test_tool_armar_plan_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod.crear_tool_armar_plan(conexion=MagicMock())

    assert tool_creada.name == "armar_plan"
    assert tool_creada.description
    assert tool_creada.args_schema is mod.ArgsArmarPlan
