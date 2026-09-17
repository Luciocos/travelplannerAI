"""Tests de conversaciones.py (persistencia de chats, D-13). Mockea la
conexion, no toca Postgres real (ver test_conversaciones_db.py para eso)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from asistente_viajes import conversaciones as mod
from asistente_viajes.agente import SesionAgente
from asistente_viajes.estado import PreferenciasViaje


def _conexion_con(fetchone_valores=None, fetchall_valor=None) -> MagicMock:
    conexion = MagicMock()
    cursor = MagicMock()
    if fetchone_valores is not None:
        cursor.fetchone.side_effect = fetchone_valores
    if fetchall_valor is not None:
        cursor.fetchall.return_value = fetchall_valor
    conexion.cursor.return_value.__enter__.return_value = cursor
    return conexion, cursor


def test_crear_conversacion_devuelve_el_id() -> None:
    conexion, _cursor = _conexion_con(fetchone_valores=[("11111111-1111-1111-1111-111111111111",)])

    id_ = mod.crear_conversacion(conexion)

    assert id_ == "11111111-1111-1111-1111-111111111111"


def test_listar_conversaciones_arma_resumenes() -> None:
    filas = [("id-1", "Cancun · 10/01-15/01", datetime(2026, 9, 17, tzinfo=UTC))]
    conexion, _cursor = _conexion_con(fetchall_valor=filas)

    resultado = mod.listar_conversaciones(conexion)

    assert len(resultado) == 1
    assert resultado[0].titulo == "Cancun · 10/01-15/01"


def test_cargar_conversacion_inexistente_devuelve_none() -> None:
    conexion, _cursor = _conexion_con(fetchone_valores=[None])

    assert mod.cargar_conversacion(conexion, "no-existe") is None


def test_cargar_conversacion_reconstruye_estado_e_historial() -> None:
    sesion_jsonb = {
        "estado": {"destino": "Cancun", "cantidad_personas": 2},
        "ultimo_plan": {"destino": "Cancun"},
        "info_destino_mostrada_para": "Cancun",
    }
    conexion, cursor = _conexion_con(fetchone_valores=[(sesion_jsonb, mod.ESQUEMA_VERSION_ACTUAL)])
    cursor.fetchall.return_value = [("asistente", "hola"), ("usuario", "quiero ir a Cancun")]

    sesion = mod.cargar_conversacion(conexion, "id-1")

    assert sesion.estado.destino == "Cancun"
    assert sesion.ultimo_plan == {"destino": "Cancun"}
    assert sesion.info_destino_mostrada_para == "Cancun"
    # se invierte el orden (la query trae DESC para el LIMIT, se muestra ASC)
    assert sesion.historial == [
        {"rol": "usuario", "texto": "quiero ir a Cancun"},
        {"rol": "asistente", "texto": "hola"},
    ]


def test_cargar_conversacion_esquema_viejo_degrada_a_estado_vacio() -> None:
    conexion, cursor = _conexion_con(fetchone_valores=[({"estado": {"destino": "Cancun"}}, 999)])
    cursor.fetchall.return_value = [("usuario", "hola")]

    sesion = mod.cargar_conversacion(conexion, "id-1")

    assert sesion.estado.destino is None  # no se reconstruyo del jsonb viejo
    assert sesion.historial == [{"rol": "usuario", "texto": "hola"}]  # el historial si se recupera


def test_titulo_automatico_sin_destino_es_none() -> None:
    sesion = SesionAgente()
    assert mod._titulo_automatico(sesion) is None


def test_titulo_automatico_con_destino_y_fechas() -> None:
    sesion = SesionAgente(
        estado=PreferenciasViaje(
            destino="Cancun", fecha_inicio=date(2027, 1, 10), fecha_fin=date(2027, 1, 15)
        )
    )
    assert mod._titulo_automatico(sesion) == "Cancun · 10/01-15/01"


def test_titulo_automatico_con_destino_sin_fechas() -> None:
    sesion = SesionAgente(estado=PreferenciasViaje(destino="Miami"))
    assert mod._titulo_automatico(sesion) == "Miami"


def test_guardar_turno_inserta_los_dos_mensajes_en_orden() -> None:
    conexion, cursor = _conexion_con(fetchone_valores=[(4,)])  # orden_actual = 4

    sesion = SesionAgente(estado=PreferenciasViaje(destino="Cancun"))
    mod.guardar_turno(conexion, "id-1", sesion, "hola", "¡Hola! ¿En qué le puedo ayudar?")

    insert_mensajes = cursor.execute.call_args_list[1]
    parametros = insert_mensajes.args[1]
    assert parametros == ("id-1", 5, "hola", "id-1", 6, "¡Hola! ¿En qué le puedo ayudar?")


def test_guardar_turno_no_pisa_titulo_puesto_a_mano() -> None:
    conexion, cursor = _conexion_con(fetchone_valores=[(0,)])

    sesion = SesionAgente(estado=PreferenciasViaje(destino="Cancun"))
    mod.guardar_turno(conexion, "id-1", sesion, "hola", "listo")

    update_conversacion = cursor.execute.call_args_list[2]
    assert "CASE WHEN titulo_manual" in update_conversacion.args[0]


def test_renombrar_conversacion_marca_titulo_manual() -> None:
    conexion, cursor = _conexion_con()

    mod.renombrar_conversacion(conexion, "id-1", "Mi viaje a Cancun")

    parametros = cursor.execute.call_args.args[1]
    assert parametros == ("Mi viaje a Cancun", "id-1")


def test_eliminar_conversacion_ejecuta_delete() -> None:
    conexion, cursor = _conexion_con()

    mod.eliminar_conversacion(conexion, "id-1")

    assert "DELETE FROM conversacion" in cursor.execute.call_args.args[0]
