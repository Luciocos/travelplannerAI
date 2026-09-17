"""Tests del orquestador (grafo.py, D-12). Mockea el LLM (rotador) y la
conexion, no toca la red ni Postgres real. Cubre los bugs reales
encontrados charlando con el agente (ver DIFICULTADES.md P-08)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from asistente_viajes import grafo as mod
from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.grafo import AccionPedida, InterpretacionTurno, procesar_turno
from asistente_viajes.tools.armar_plan import (
    ActividadDelPlan,
    DiaDelPlan,
    ErrorFechasIncompletas,
    PlanDeViaje,
)
from asistente_viajes.tools.recomendar_actividades import ActividadRecomendada
from asistente_viajes.tools.responder_faq_viajero import RespuestaFaq

HOY = date(2026, 9, 17)


@pytest.fixture(autouse=True)
def _sin_recomendacion_de_regalo_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    """planificar agrega una recomendacion de regalo (recomendar_actividades)
    cada vez que hay destino y falta algun otro dato. Sin mockear esto,
    cualquier test con un destino piloto real termina cargando el modelo
    de embeddings real (lento) y pegandole a una conexion MagicMock sin
    sentido. Los tests que quieren probar esa accion la vuelven a
    monkeypatchear explicitamente, pisando este default."""
    monkeypatch.setattr(mod, "recomendar_actividades", lambda *_a, **_k: [])


def _rotador_con_interpretacion(interpretacion: InterpretacionTurno) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = interpretacion
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    return rotador


def _turno(rotador, mensaje, estado=None, historial=None, ultimo_plan=None, info_destino_para=None):
    return procesar_turno(
        conexion=MagicMock(),
        rotador=rotador,
        mensaje=mensaje,
        historial=historial or [],
        estado=(estado or PreferenciasViaje()).model_dump(mode="json"),
        ultimo_plan=ultimo_plan,
        info_destino_mostrada_para=info_destino_para,
        hoy=HOY,
    )


# --- interpretar / actualizar_estado -----------------------------------


def test_actualizar_estado_deriva_tipo_destino_del_destino() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno(destino="Barcelona"))
    resultado = _turno(rotador, "quiero ir a Barcelona")
    assert resultado["estado"]["tipo_destino"] == "ciudad"


def test_actualizar_estado_parsea_fechas_iso_de_texto() -> None:
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(fecha_inicio="2027-01-10", fecha_fin="2027-01-15")
    )
    resultado = _turno(rotador, "del 10 al 15 de enero de 2027")
    assert resultado["estado"]["fecha_inicio"] == "2027-01-10"
    assert resultado["estado"]["fecha_fin"] == "2027-01-15"


def test_actualizar_estado_ignora_fecha_invalida_sin_romper_el_turno() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno(fecha_inicio="no es una fecha"))
    resultado = _turno(rotador, "en algun momento")
    assert resultado["estado"]["fecha_inicio"] is None
    assert resultado["respuesta_texto"]  # el turno sigue, no explota


def test_actualizar_estado_no_pisa_destino_ya_cargado() -> None:
    estado = PreferenciasViaje(destino="Miami")
    rotador = _rotador_con_interpretacion(InterpretacionTurno(cantidad_personas=3))
    resultado = _turno(rotador, "somos 3", estado=estado)
    assert resultado["estado"]["destino"] == "Miami"
    assert resultado["estado"]["cantidad_personas"] == 3


def test_actualizar_estado_usar_sugerencias_completa_lo_que_falta() -> None:
    estado = PreferenciasViaje(destino="Cancun")
    rotador = _rotador_con_interpretacion(InterpretacionTurno(usar_sugerencias=True))
    resultado = _turno(rotador, "usar sugerencias", estado=estado)
    assert resultado["estado"]["presupuesto"] == "medio"
    assert resultado["estado"]["cantidad_personas"] == 2
    assert resultado["estado"]["duracion_dias"] == 5


def test_destino_fuera_de_alcance_no_se_pierde_en_silencio() -> None:
    """Bug real: 'Quiero ir a Tokio' quedaba sin destino y sin ningun
    mensaje que lo explicara."""
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(destino_fuera_de_alcance="Tokio", intereses=["comida"])
    )
    resultado = _turno(rotador, "quiero ir a Tokio, me gusta la comida")
    assert resultado["estado"]["destino"] is None
    assert "Tokio" in resultado["respuesta_texto"]
    assert "Barcelona" in resultado["respuesta_texto"]


# --- planificar ----------------------------------------------------------


def test_planificar_pide_todo_lo_que_falta_de_una_vez() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    resultado = _turno(rotador, "hola")
    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos
    assert "Barcelona" in resultado["respuesta_texto"]
    assert "usar sugerencias" in resultado["respuesta_texto"]


def test_planificar_da_una_respuesta_util_ademas_de_la_pregunta_si_hay_destino(monkeypatch) -> None:
    """Bug real: preguntar y preguntar sin nunca dar nada util."""
    estado = PreferenciasViaje(destino="Cancun")
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    monkeypatch.setattr(
        mod,
        "recomendar_actividades",
        lambda *a, **k: [
            ActividadRecomendada(
                nombre="El Meco", categoria="historic", justificacion="Sitio maya."
            )
        ],
    )

    resultado = _turno(rotador, "hola", estado=estado)

    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos
    assert "recomendar_actividades" in tipos
    assert "El Meco" in resultado["respuesta_texto"]


def test_planificar_no_pide_datos_si_ya_esta_completo(monkeypatch) -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    resultado = _turno(rotador, "hola", estado=estado)
    assert resultado["pendientes"] == []


def test_planificar_multiples_acciones_en_un_solo_mensaje(monkeypatch) -> None:
    """El pedido central: procesar varias demandas del cliente en un
    solo turno, no solo una tool por vez."""
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(
            acciones=[
                AccionPedida(tipo="armar_plan"),
                AccionPedida(tipo="recomendar_locales"),
                AccionPedida(tipo="responder_faq_viajero"),
            ]
        )
    )
    monkeypatch.setattr(
        mod,
        "armar_plan",
        lambda *a, **k: PlanDeViaje(
            destino="Cancun",
            dias=[
                DiaDelPlan(
                    dia=1,
                    actividades=[
                        ActividadDelPlan(nombre="Museo", categoria="museums", costo_estimado=5.0)
                    ],
                    costo_actividades=5.0,
                    gasto_estimado_dia=0.0,
                    costo_dia=5.0,
                )
            ],
            costo_actividades_total=5.0,
            gasto_estimado_total=0.0,
            costo_total_estimado=5.0,
            cantidad_personas=2,
            costo_total_grupo=10.0,
        ),
    )
    monkeypatch.setattr(mod, "guardar_itinerario", lambda *a, **k: 1)
    monkeypatch.setattr(mod, "recomendar_locales", lambda *a, **k: [])
    monkeypatch.setattr(
        mod,
        "responder_faq_viajero",
        lambda *a, **k: RespuestaFaq(respondida=True, respuesta="Tome precauciones."),
    )

    resultado = _turno(rotador, "armame el plan, decime donde comer y si es seguro", estado=estado)

    assert len(resultado["pendientes"]) == 3
    assert "Museo" in resultado["respuesta_texto"]
    assert "No encontré locales" in resultado["respuesta_texto"]
    assert "Tome precauciones." in resultado["respuesta_texto"]


def test_planificar_reconstruye_el_plan_solo_si_cambio_un_dato_relevante(monkeypatch) -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    plan_previo = {"destino": "Cancun"}
    rotador = _rotador_con_interpretacion(InterpretacionTurno(cantidad_personas=4))
    llamado = MagicMock(
        return_value=PlanDeViaje(
            destino="Cancun",
            dias=[],
            costo_actividades_total=0.0,
            gasto_estimado_total=0.0,
            costo_total_estimado=0.0,
            cantidad_personas=4,
            costo_total_grupo=0.0,
        )
    )
    monkeypatch.setattr(mod, "armar_plan", llamado)
    monkeypatch.setattr(mod, "guardar_itinerario", lambda *a, **k: 1)

    resultado = _turno(rotador, "somos 4 en vez de 2", estado=estado, ultimo_plan=plan_previo)

    llamado.assert_called_once()
    assert resultado["estado"]["cantidad_personas"] == 4


def test_planificar_no_reconstruye_el_plan_si_nada_relevante_cambio(monkeypatch) -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    plan_previo = {"destino": "Cancun"}
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    llamado = MagicMock()
    monkeypatch.setattr(mod, "armar_plan", llamado)

    _turno(rotador, "gracias", estado=estado, ultimo_plan=plan_previo)

    llamado.assert_not_called()


# --- ejecutar_acciones: aislamiento de errores ---------------------------


def test_armar_plan_sin_fechas_ni_duracion_no_rompe_el_turno(monkeypatch) -> None:
    """Bug real: pedir el plan sin fechas tiraba un TypeError crudo."""
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="armar_plan")])
    )

    def _falla(*_a, **_k):
        raise ErrorFechasIncompletas("faltan fechas")

    monkeypatch.setattr(mod, "armar_plan", _falla)

    resultado = _turno(rotador, "armame el plan", estado=estado)

    assert "fechas exactas" in resultado["respuesta_texto"].lower()


def test_una_accion_rota_no_tira_abajo_las_demas(monkeypatch) -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(
            acciones=[
                AccionPedida(tipo="recomendar_locales"),
                AccionPedida(tipo="responder_faq_viajero"),
            ]
        )
    )

    def _falla(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "recomendar_locales", _falla)
    monkeypatch.setattr(
        mod,
        "responder_faq_viajero",
        lambda *a, **k: RespuestaFaq(respondida=True, respuesta="Todo bien."),
    )

    resultado = _turno(rotador, "donde como y es seguro", estado=estado)

    assert "Todo bien." in resultado["respuesta_texto"]
    assert "problema puntual" in resultado["respuesta_texto"]


# --- disparar_info_destino -----------------------------------------------


def test_info_destino_se_dispara_una_vez_por_destino(monkeypatch) -> None:
    from asistente_viajes.tools.info_destino import InfoClima, InfoDestino, InfoIdiomaMoneda

    estado = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2027, 1, 10), fecha_fin=date(2027, 1, 13)
    )
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    monkeypatch.setattr(
        mod,
        "info_destino",
        lambda **k: InfoDestino(
            destino="Cancun",
            clima=InfoClima(disponible=True, detalle="Pronostico en vivo."),
            idioma_moneda=InfoIdiomaMoneda(idioma="español", moneda="MXN"),
        ),
    )

    primero = _turno(rotador, "listo", estado=estado)
    assert "Pronostico en vivo" in primero["respuesta_texto"]

    segundo = _turno(
        rotador, "gracias", estado=estado, info_destino_para=primero["info_destino_mostrada_para"]
    )
    assert "Pronostico en vivo" not in segundo["respuesta_texto"]


def test_info_destino_se_re_dispara_si_cambia_el_destino(monkeypatch) -> None:
    from asistente_viajes.tools.info_destino import InfoClima, InfoDestino, InfoIdiomaMoneda

    monkeypatch.setattr(
        mod,
        "info_destino",
        lambda **k: InfoDestino(
            destino=k["destino"],
            clima=InfoClima(disponible=True, detalle="Pronostico en vivo."),
            idioma_moneda=InfoIdiomaMoneda(idioma="español", moneda="USD"),
        ),
    )
    estado_cancun = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2027, 1, 10), fecha_fin=date(2027, 1, 13)
    )
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    primero = _turno(rotador, "listo", estado=estado_cancun)

    estado_miami = PreferenciasViaje(
        destino="Miami", fecha_inicio=date(2027, 2, 1), fecha_fin=date(2027, 2, 3)
    )
    rotador2 = _rotador_con_interpretacion(InterpretacionTurno())
    segundo = _turno(
        rotador2,
        "mejor Miami",
        estado=estado_miami,
        info_destino_para=primero["info_destino_mostrada_para"],
    )

    assert "Pronostico en vivo" in segundo["respuesta_texto"]
    assert segundo["info_destino_mostrada_para"] == "Miami"


# --- redactar / memoria y small talk --------------------------------------


def test_conversar_responde_desde_el_historial_sin_tools(monkeypatch) -> None:
    """Bug real: preguntas de recap ('¿a que destino dijimos?') devolvian
    un texto enlatado en vez de responder con lo que ya se sabe."""
    estado = PreferenciasViaje(
        destino="Miami",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        fecha_inicio=date(2027, 8, 1),
        fecha_fin=date(2027, 8, 7),
        cantidad_personas=3,
    )
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    rotador.invocar.return_value = MagicMock(
        content="Habíamos quedado en Miami, del 1 al 7 de agosto."
    )

    resultado = _turno(
        rotador, "a que destino dijimos que queria ir?", estado=estado, info_destino_para="Miami"
    )

    assert resultado["respuesta_texto"] == "Habíamos quedado en Miami, del 1 al 7 de agosto."
    prompt_enviado = rotador.invocar.call_args.args[0]
    assert "Miami" in prompt_enviado


def test_conversar_usa_una_respuesta_de_reserva_si_falla_el_llm() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    rotador.invocar.side_effect = RuntimeError("sin cuota")

    resultado = _turno(rotador, "gracias")

    assert resultado["respuesta_texto"]  # nunca vacio ni una excepcion


def test_interpretar_fallido_no_rompe_el_turno() -> None:
    rotador = MagicMock()
    rotador.con_salida_estructurada.return_value.invoke.side_effect = RuntimeError("sin cuota")
    rotador.invocar.return_value = MagicMock(content="Estoy para ayudarlo.")

    resultado = _turno(rotador, "hola")

    assert resultado["respuesta_texto"]


def test_grafo_compila_y_tiene_los_nodos_esperados() -> None:
    grafo = mod.construir_grafo()
    nodos = set(grafo.get_graph().nodes.keys())
    for nombre in (
        "interpretar",
        "actualizar_estado",
        "planificar",
        "ejecutar_acciones",
        "disparar_info_destino",
        "redactar",
    ):
        assert nombre in nodos


def test_recursion_limit_explicito_no_default_gigante() -> None:
    """LangGraph 1.2 tiene un recursion_limit por defecto muy grande
    (10007): si el grafo entrara en loop, tardaria mucho en fallar. Se
    pasa un limite chico y explicito en cada invoke (ver procesar_turno)."""
    import inspect

    fuente = inspect.getsource(mod.procesar_turno)
    assert "recursion_limit" in fuente


@pytest.mark.parametrize("valor", [None, ""])
def test_pedir_datos_no_se_confunde_con_mensaje_vacio(valor) -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    resultado = _turno(rotador, valor or "")
    assert resultado["respuesta_texto"]
