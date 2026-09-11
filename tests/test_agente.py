"""Tests del orquestador (RF11, RF12, Fase 5). Mockea el LLM (decision y
tools) y la conexion, no toca la red ni Postgres real."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from asistente_viajes import agente as mod
from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.tools.armar_plan import ActividadDelPlan, DiaDelPlan, PlanDeViaje
from asistente_viajes.tools.info_destino import InfoClima, InfoDestino, InfoIdiomaMoneda
from asistente_viajes.tools.recomendar_actividades import ActividadRecomendada


def _rotador_con_decision(accion: str, cantidad_resultados: int | None = None) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = mod.DecisionAccion(
        accion=accion, cantidad_resultados=cantidad_resultados
    )
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    return rotador


def test_decidir_accion_llama_al_llm_con_el_estado_y_lo_faltante() -> None:
    rotador = _rotador_con_decision("completar_slots")
    estado = PreferenciasViaje(destino="Cancun")

    decision = mod._decidir_accion(rotador, "quiero ir a Cancun", estado)

    assert decision.accion == "completar_slots"
    assert decision.cantidad_resultados is None
    rotador.con_salida_estructurada.assert_called_once_with(mod.DecisionAccion)


def test_decidir_accion_propaga_cantidad_resultados_pedida() -> None:
    rotador = _rotador_con_decision("recomendar_actividades", cantidad_resultados=5)
    estado = PreferenciasViaje(destino="Cancun", intereses=["historia"])

    decision = mod._decidir_accion(rotador, "dame 5 opciones", estado)

    assert decision.cantidad_resultados == 5


def test_procesar_mensaje_completar_slots_actualiza_la_sesion(monkeypatch) -> None:
    rotador = _rotador_con_decision("completar_slots")
    nuevo_estado = PreferenciasViaje(destino="Cancun")
    monkeypatch.setattr(mod, "completar_slots", lambda *_, **__: (nuevo_estado, "¿Qué tipo de destino buscás?"))

    sesion = mod.SesionAgente()
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "quiero ir a Cancun")

    assert sesion.estado is nuevo_estado
    assert respuesta == "¿Qué tipo de destino buscás?"


def test_procesar_mensaje_armar_plan_llama_a_la_tool_y_persiste(monkeypatch) -> None:
    rotador = _rotador_con_decision("armar_plan")
    plan = PlanDeViaje(
        destino="Cancun",
        dias=[DiaDelPlan(dia=1, actividades=[ActividadDelPlan(nombre="Museo", categoria="museums", costo_estimado=10.0)], costo_dia=10.0)],
        costo_total_estimado=10.0,
        cantidad_personas=1,
        costo_total_grupo=10.0,
    )
    monkeypatch.setattr(mod, "armar_plan", lambda *_, **__: plan)
    guardar_llamado = MagicMock()
    monkeypatch.setattr(mod, "guardar_itinerario", guardar_llamado)

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun"))
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "armame el plan")

    guardar_llamado.assert_called_once()
    assert "Museo" in respuesta
    assert "Cancun" in respuesta


def test_procesar_mensaje_recomendar_actividades(monkeypatch) -> None:
    rotador = _rotador_con_decision("recomendar_actividades")
    actividad = ActividadRecomendada(nombre="El Meco", categoria="historic", justificacion="Es un sitio maya real.")
    llamada = MagicMock(return_value=[actividad])
    monkeypatch.setattr(mod, "recomendar_actividades", llamada)

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun", intereses=["historia"]))
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "qué puedo visitar")

    assert "El Meco" in respuesta
    assert "sitio maya real" in respuesta
    assert llamada.call_args.kwargs["k"] == mod.CANTIDAD_RESULTADOS_DEFECTO


def test_procesar_mensaje_recomendar_actividades_usa_cantidad_pedida(monkeypatch) -> None:
    rotador = _rotador_con_decision("recomendar_actividades", cantidad_resultados=5)
    llamada = MagicMock(return_value=[])
    monkeypatch.setattr(mod, "recomendar_actividades", llamada)

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun", intereses=["historia"]))
    mod.procesar_mensaje(MagicMock(), rotador, sesion, "dame 5 opciones")

    assert llamada.call_args.kwargs["k"] == 5


def test_procesar_mensaje_recomendar_locales(monkeypatch) -> None:
    rotador = _rotador_con_decision("recomendar_locales")
    from asistente_viajes.tools.recomendar_locales import LocalRecomendado

    local = LocalRecomendado(nombre="Mercado 28", categoria="shops", direccion=None, rango_precio="$$", justificacion="Vende artesanias tipicas.")
    llamada = MagicMock(return_value=[local])
    monkeypatch.setattr(mod, "recomendar_locales", llamada)

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun"))
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "donde compro artesanias")

    assert "Mercado 28" in respuesta
    assert llamada.call_args.kwargs["k"] == mod.CANTIDAD_RESULTADOS_DEFECTO


def test_procesar_mensaje_responder_faq_viajero(monkeypatch) -> None:
    rotador = _rotador_con_decision("responder_faq_viajero")
    from asistente_viajes.tools.responder_faq_viajero import RespuestaFaq

    respuesta_faq = RespuestaFaq(
        tema="Taxis y tarifas", categoria="estafas", respuesta="Acordá el precio antes de subir."
    )
    llamada = MagicMock(return_value=[respuesta_faq])
    monkeypatch.setattr(mod, "responder_faq_viajero", llamada)

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun"))
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "es seguro tomar un taxi")

    assert "Acordá el precio antes de subir" in respuesta
    assert llamada.call_args.kwargs["k"] == mod.CANTIDAD_RESULTADOS_DEFECTO


def test_coordenadas_destino_conocido(monkeypatch) -> None:
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: ("Cancun", {"pais": "Mexico", "lat": 21.1, "lon": -86.8}))

    assert mod._coordenadas_destino("Cancun") == {"pais": "Mexico", "lat": 21.1, "lon": -86.8}


def test_coordenadas_destino_desconocido_devuelve_none(monkeypatch) -> None:
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)

    assert mod._coordenadas_destino("Narnia") is None


def _info_destino_falsa() -> InfoDestino:
    return InfoDestino(
        destino="Cancun",
        clima=InfoClima(disponible=True, detalle="Pronostico en vivo de Open-Meteo."),
        idioma_moneda=InfoIdiomaMoneda(idioma="espanol", moneda="MXN"),
    )


def test_disparar_info_destino_se_dispara_una_sola_vez(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_coordenadas_destino", lambda destino: {"pais": "Mexico", "lat": 21.1, "lon": -86.8})
    monkeypatch.setattr(mod, "info_destino", lambda **_: _info_destino_falsa())

    sesion = mod.SesionAgente(
        estado=PreferenciasViaje(destino="Cancun", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 3))
    )

    primera = mod._disparar_info_destino_si_corresponde(sesion)
    segunda = mod._disparar_info_destino_si_corresponde(sesion)

    assert primera is not None
    assert segunda is None
    assert sesion.info_destino_disparada is True


def test_disparar_info_destino_no_dispara_sin_fechas(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_coordenadas_destino", lambda destino: {"pais": "Mexico", "lat": 21.1, "lon": -86.8})

    sesion = mod.SesionAgente(estado=PreferenciasViaje(destino="Cancun"))

    assert mod._disparar_info_destino_si_corresponde(sesion) is None
    assert sesion.info_destino_disparada is False


def test_disparar_info_destino_no_dispara_si_destino_desconocido(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_coordenadas_destino", lambda destino: None)

    sesion = mod.SesionAgente(
        estado=PreferenciasViaje(destino="Narnia", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 3))
    )

    assert mod._disparar_info_destino_si_corresponde(sesion) is None


def test_procesar_mensaje_incluye_info_destino_cuando_se_confirma(monkeypatch) -> None:
    rotador = _rotador_con_decision("completar_slots")
    nuevo_estado = PreferenciasViaje(
        destino="Cancun", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 3)
    )
    monkeypatch.setattr(mod, "completar_slots", lambda *_, **__: (nuevo_estado, None))
    monkeypatch.setattr(mod, "_coordenadas_destino", lambda destino: {"pais": "Mexico", "lat": 21.1, "lon": -86.8})
    monkeypatch.setattr(mod, "info_destino", lambda **_: _info_destino_falsa())

    sesion = mod.SesionAgente()
    respuesta = mod.procesar_mensaje(MagicMock(), rotador, sesion, "viajamos del 1 al 3 de noviembre a Cancun")

    assert "Pronostico en vivo" in respuesta
    assert "espanol" in respuesta
