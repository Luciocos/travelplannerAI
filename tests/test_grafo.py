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
from asistente_viajes.services.rapidapi.models import Alojamiento, OpcionVuelo
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


PROSA_REDACTADA = "(prosa redactada por el LLM)"


def _rotador_con_interpretacion(interpretacion: InterpretacionTurno) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = interpretacion
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    # Desde D-22 el texto del turno lo escribe el LLM (nodo_redactar via
    # rotador.invocar), asi que devolvemos una prosa fija: estos tests
    # verifican QUE HECHOS llegan al redactor, no como los redacta. Lo
    # contrario seria testear la salida de un modelo generativo.
    rotador.invocar.return_value.content = PROSA_REDACTADA
    return rotador


def _hechos_del_turno(rotador: MagicMock) -> str:
    """El prompt con el que se llamo a redactar. Ahi estan los resultados,
    los faltantes y los ajustes del turno: es el contrato que reemplaza a
    las plantillas de Python que se asertaban antes de la Fase 7E."""
    assert rotador.invocar.called, "no se llamo a redactar en este turno"
    return rotador.invocar.call_args[0][0]


def _turno(
    rotador,
    mensaje,
    estado=None,
    historial=None,
    ultimo_plan=None,
    info_destino_para=None,
    pedir_datos_para=None,
):
    return procesar_turno(
        conexion=MagicMock(),
        rotador=rotador,
        mensaje=mensaje,
        historial=historial or [],
        estado=(estado or PreferenciasViaje()).model_dump(mode="json"),
        ultimo_plan=ultimo_plan,
        info_destino_mostrada_para=info_destino_para,
        pedir_datos_mostrado_para=pedir_datos_para,
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
    hechos = _hechos_del_turno(rotador)
    assert "Tokio" in hechos
    assert "Barcelona" in hechos


# --- planificar ----------------------------------------------------------


def test_planificar_pide_todo_lo_que_falta_de_una_vez() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno())
    resultado = _turno(rotador, "hola")
    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos
    # La pregunta ya no se arma en Python (D-22 redefine D-14): lo que se
    # verifica es que el redactor reciba la lista completa de faltantes,
    # para poder pedirlos todos de una vez con sus palabras.
    hechos = _hechos_del_turno(rotador)
    for slot in ("destino", "intereses", "presupuesto", "cantidad_personas"):
        assert slot in hechos


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


# --- pedir_datos no se repite sin motivo (P-13) ---------------------------


def _estado_con_intereses_faltante() -> PreferenciasViaje:
    return PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        presupuesto="medio",
        fecha_inicio=date(2026, 12, 1),
        fecha_fin=date(2026, 12, 5),
        cantidad_personas=2,
    )  # falta unicamente "intereses"


def test_pedir_datos_no_se_repite_si_nada_cambio_y_no_hay_pedido() -> None:
    """Bug real: un 'gracias' sin datos nuevos repetia la misma pregunta
    consolidada de siempre en vez de reconocer el agradecimiento."""
    rotador = _rotador_con_interpretacion(InterpretacionTurno())

    resultado = _turno(
        rotador,
        "gracias, me sirvió mucho",
        estado=_estado_con_intereses_faltante(),
        pedir_datos_para=["intereses"],
    )

    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" not in tipos


def test_pedir_datos_se_repite_si_algo_cambio_aunque_ya_se_habia_preguntado() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno(cantidad_personas=4))

    resultado = _turno(
        rotador,
        "somos 4 en vez de 2",
        estado=_estado_con_intereses_faltante(),
        pedir_datos_para=["intereses"],
    )

    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos


def test_pedir_datos_se_repite_si_hay_un_pedido_explicito_aunque_ya_se_habia_preguntado() -> None:
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="armar_plan")])
    )

    resultado = _turno(
        rotador,
        "armame el plan",
        estado=_estado_con_intereses_faltante(),
        pedir_datos_para=["intereses"],
    )

    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos


def test_pedir_datos_se_repite_la_primera_vez_aunque_nada_cambie() -> None:
    """pedir_datos_mostrado_para arranca en None: la primera pregunta
    siempre tiene que salir, aunque "nada cambio" respecto de un estado
    vacio inicial (no hay confundir "primera vez" con "ya se pregunto")."""
    rotador = _rotador_con_interpretacion(InterpretacionTurno())

    resultado = _turno(rotador, "hola", estado=_estado_con_intereses_faltante())

    tipos = [p["tipo"] for p in resultado["pendientes"]]
    assert "pedir_datos" in tipos


def test_pedir_datos_mostrado_para_se_limpia_cuando_ya_no_falta_nada() -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["naturaleza"],
        presupuesto="medio",
        fecha_inicio=date(2026, 12, 1),
        fecha_fin=date(2026, 12, 5),
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(InterpretacionTurno())

    resultado = _turno(rotador, "hola", estado=estado, pedir_datos_para=["intereses"])

    assert resultado["pedir_datos_mostrado_para"] is None


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
    assert "Tome precauciones." in _hechos_del_turno(rotador)


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

    # planificar ni siquiera deja pasar la accion (precondicion: tiene_cuando),
    # asi que el turno no explota y el redactor recibe el faltante para
    # poder pedirlo con sus palabras.
    assert resultado["respuesta_texto"]
    hechos = _hechos_del_turno(rotador)
    assert "fecha_inicio" in hechos


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

    _turno(rotador, "donde como y es seguro", estado=estado)

    hechos = _hechos_del_turno(rotador)
    assert "Todo bien." in hechos
    assert "problema tecnico puntual" in hechos


def test_cada_accion_usa_su_propia_consulta_no_el_mensaje_completo(monkeypatch) -> None:
    """Bug real: 'armame el plan, decime donde comer y si es seguro de
    noche' le pasaba el MENSAJE COMPLETO como consulta tanto a
    recomendar_locales como a responder_faq_viajero, diluyendo la
    busqueda semantica de cada una (la de seguridad terminaba hablando
    del plan de viaje)."""
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
                AccionPedida(tipo="recomendar_locales", consulta="donde comer"),
                AccionPedida(tipo="responder_faq_viajero", consulta="si es seguro de noche"),
            ]
        )
    )
    consultas_recibidas = {}

    def _locales(_conexion, _rotador, _destino, consulta, k):
        consultas_recibidas["locales"] = consulta
        return []

    def _faq(_conexion, _rotador, _destino, consulta, k):
        consultas_recibidas["faq"] = consulta
        return RespuestaFaq(respondida=True, respuesta="ok")

    monkeypatch.setattr(mod, "recomendar_locales", _locales)
    monkeypatch.setattr(mod, "responder_faq_viajero", _faq)

    _turno(rotador, "armame el plan, decime donde comer y si es seguro de noche", estado=estado)

    assert consultas_recibidas["locales"] == "donde comer"
    assert consultas_recibidas["faq"] == "si es seguro de noche"


def test_accion_sin_consulta_propia_usa_el_mensaje_completo(monkeypatch) -> None:
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        duracion_dias=3,
        cantidad_personas=2,
    )
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="recomendar_locales")])
    )
    consultas_recibidas = {}

    def _locales(_conexion, _rotador, _destino, consulta, k):
        consultas_recibidas["locales"] = consulta
        return []

    monkeypatch.setattr(mod, "recomendar_locales", _locales)

    _turno(rotador, "donde como algo tipico y barato", estado=estado)

    assert consultas_recibidas["locales"] == "donde como algo tipico y barato"


# --- buscar_alojamiento / buscar_vuelos (RF6/RF7) -------------------------


def _estado_completo(**overrides) -> PreferenciasViaje:
    base = {
        "destino": "Barcelona",
        "tipo_destino": "ciudad",
        "intereses": ["historia"],
        "presupuesto": "medio",
        "fecha_inicio": date(2027, 3, 5),
        "fecha_fin": date(2027, 3, 10),
        "cantidad_personas": 2,
    }
    base.update(overrides)
    return PreferenciasViaje(**base)


def test_actualizar_estado_extrae_origen() -> None:
    rotador = _rotador_con_interpretacion(InterpretacionTurno(origen="Buenos Aires"))
    resultado = _turno(rotador, "el vuelo sale de Buenos Aires")
    assert resultado["estado"]["origen"] == "Buenos Aires"


def test_planificar_pide_fechas_exactas_si_solo_hay_duracion_dias() -> None:
    estado = _estado_completo(fecha_inicio=None, fecha_fin=None, duracion_dias=5)
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="buscar_alojamiento")])
    )
    resultado = _turno(rotador, "buscame un hotel", estado=estado)
    assert resultado["pendientes"] == [{"tipo": "pedir_fechas_exactas"}]
    assert "fechas exactas" in _hechos_del_turno(rotador).lower()


def test_planificar_pide_origen_si_falta_para_vuelos() -> None:
    estado = _estado_completo()
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="buscar_vuelos")])
    )
    resultado = _turno(rotador, "quiero vuelos", estado=estado)
    assert resultado["pendientes"] == [{"tipo": "pedir_origen_vuelo"}]
    assert "que ciudad sale el vuelo" in _hechos_del_turno(rotador).lower()


def test_buscar_alojamiento_se_ejecuta_con_datos_completos(monkeypatch) -> None:
    estado = _estado_completo(cantidad_personas=3)
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="buscar_alojamiento")])
    )
    llamada = MagicMock(
        return_value=[
            Alojamiento(nombre="Hotel Test", proveedor="booking", precio_total=500.0, moneda="USD")
        ]
    )
    monkeypatch.setattr(mod, "buscar_alojamiento", llamada)

    resultado = _turno(rotador, "buscame alojamiento", estado=estado)

    assert llamada.call_args.args[0] is not None
    assert llamada.call_args.kwargs["adultos"] == 3
    assert llamada.call_args.kwargs["habitaciones"] == 2  # ceil(3/2)
    assert "Hotel Test" in resultado["respuesta_texto"]
    assert "500" in resultado["respuesta_texto"]


def test_buscar_alojamiento_marca_los_datos_de_ejemplo(monkeypatch) -> None:
    estado = _estado_completo()
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="buscar_alojamiento")])
    )
    monkeypatch.setattr(
        mod,
        "buscar_alojamiento",
        lambda *a, **k: [
            Alojamiento(
                nombre="Hotel Fixture",
                proveedor="booking",
                precio_total=100.0,
                moneda="USD",
                es_fixture=True,
            )
        ],
    )

    resultado = _turno(rotador, "buscame alojamiento", estado=estado)

    assert "dato de ejemplo" in resultado["respuesta_texto"]


def test_buscar_vuelos_se_ejecuta_con_origen(monkeypatch) -> None:
    estado = _estado_completo(origen="Buenos Aires")
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="buscar_vuelos")])
    )
    llamada = MagicMock(
        return_value=[
            OpcionVuelo(
                proveedor="fly_scraper",
                precio_total=300.0,
                moneda="USD",
                aerolineas=["Aerolineas Test"],
                escalas=0,
            )
        ]
    )
    monkeypatch.setattr(mod, "buscar_vuelos", llamada)

    resultado = _turno(rotador, "buscame vuelos", estado=estado)

    assert llamada.call_args.args[1] == "Buenos Aires"  # args[0] es la conexion
    assert "Aerolineas Test" in resultado["respuesta_texto"]


# --- convertir_moneda (D-18) -----------------------------------------------


def test_convertir_moneda_pide_el_plan_primero_si_no_hay_ninguno() -> None:
    estado = _estado_completo()
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="convertir_moneda")])
    )
    resultado = _turno(rotador, "cuanto es en pesos", estado=estado)
    assert resultado["pendientes"] == [{"tipo": "pedir_plan_para_convertir"}]
    assert "no hay un plan armado" in _hechos_del_turno(rotador).lower()


def test_convertir_moneda_convierte_el_costo_del_ultimo_plan(monkeypatch) -> None:
    estado = _estado_completo()
    plan_previo = {"destino": "Barcelona", "costo_total_grupo": 500.0, "moneda": "USD"}
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="convertir_moneda", moneda_destino="ARS")])
    )
    llamada = MagicMock()
    llamada.return_value.detalle = "USD 500 = ARS 750000 (dólar oficial)."
    monkeypatch.setattr(mod, "convertir_desde_usd", llamada)

    _turno(rotador, "cuanto es en pesos", estado=estado, ultimo_plan=plan_previo)

    llamada.assert_called_once_with(500.0, "ARS")
    assert "750000" in _hechos_del_turno(rotador)


def test_convertir_moneda_usa_ars_por_defecto_sin_moneda_explicita(monkeypatch) -> None:
    estado = _estado_completo()
    plan_previo = {"destino": "Barcelona", "costo_total_grupo": 200.0, "moneda": "USD"}
    rotador = _rotador_con_interpretacion(
        InterpretacionTurno(acciones=[AccionPedida(tipo="convertir_moneda")])
    )
    llamada = MagicMock()
    llamada.return_value.detalle = "listo"
    monkeypatch.setattr(mod, "convertir_desde_usd", llamada)

    _turno(rotador, "cuanto sale eso?", estado=estado, ultimo_plan=plan_previo)

    llamada.assert_called_once_with(200.0, mod.MONEDA_DESTINO_DEFECTO)


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

    assert "Habíamos quedado en Miami" in resultado["respuesta_texto"]
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
