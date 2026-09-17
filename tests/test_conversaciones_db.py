"""Tests de integracion de conversaciones.py contra Postgres real.

Se saltan automaticamente si TEST_DATABASE_URL no esta seteada o la base
no responde: no forman parte de la corrida normal de `pytest` (que nunca
toca la red ni una base real), son para correr a mano con
`docker compose up -d` levantado, o en CI donde TEST_DATABASE_URL apunta
al Postgres de servicio.

TEST_DATABASE_URL es una variable separada de DATABASE_URL a proposito:
conftest.py borra DATABASE_URL de os.environ en cada test (para aislar a
los demas tests del .env real de quien los corre), asi que estos tests
necesitan su propio nombre de variable."""

from __future__ import annotations

import os

import psycopg
import pytest

from asistente_viajes import conversaciones as mod
from asistente_viajes.agente import SesionAgente
from asistente_viajes.estado import PreferenciasViaje

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _conexion_disponible() -> bool:
    if not TEST_DATABASE_URL:
        return False
    try:
        with psycopg.connect(TEST_DATABASE_URL, connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not _conexion_disponible(),
        reason="TEST_DATABASE_URL no seteada o Postgres no disponible (docker compose up -d)",
    ),
]


@pytest.fixture
def conexion():
    with psycopg.connect(TEST_DATABASE_URL) as conexion:
        yield conexion
        conexion.rollback()  # cada test limpia lo que escribio


def test_crear_cargar_y_guardar_turno_de_punta_a_punta(conexion) -> None:
    conversacion_id = mod.crear_conversacion(conexion)

    sesion = mod.cargar_conversacion(conexion, conversacion_id)
    assert sesion is not None
    assert sesion.historial == []
    assert sesion.estado.destino is None

    sesion.estado = PreferenciasViaje(destino="Cancun", cantidad_personas=2)
    mod.guardar_turno(
        conexion, conversacion_id, sesion, "quiero ir a Cancun", "¡Buenísimo destino!"
    )

    recargada = mod.cargar_conversacion(conexion, conversacion_id)
    assert recargada.estado.destino == "Cancun"
    assert recargada.historial == [
        {"rol": "usuario", "texto": "quiero ir a Cancun"},
        {"rol": "asistente", "texto": "¡Buenísimo destino!"},
    ]

    conexion.commit()


def test_listar_conversaciones_incluye_la_nueva(conexion) -> None:
    conversacion_id = mod.crear_conversacion(conexion)
    conexion.commit()

    resumenes = mod.listar_conversaciones(conexion)

    assert any(resumen.id == conversacion_id for resumen in resumenes)


def test_titulo_automatico_se_actualiza_solo_hasta_que_se_renombra(conexion) -> None:
    conversacion_id = mod.crear_conversacion(conexion)
    sesion = SesionAgente(estado=PreferenciasViaje(destino="Miami"))

    mod.guardar_turno(conexion, conversacion_id, sesion, "hola", "listo")
    conexion.commit()
    [resumen] = [r for r in mod.listar_conversaciones(conexion) if r.id == conversacion_id]
    assert resumen.titulo == "Miami"

    mod.renombrar_conversacion(conexion, conversacion_id, "Mi viaje")
    conexion.commit()

    sesion.estado = PreferenciasViaje(destino="Barcelona")
    mod.guardar_turno(conexion, conversacion_id, sesion, "mejor Barcelona", "listo")
    conexion.commit()

    [resumen] = [r for r in mod.listar_conversaciones(conexion) if r.id == conversacion_id]
    assert resumen.titulo == "Mi viaje"  # no lo piso el titulo automatico


def test_eliminar_conversacion_borra_los_mensajes_en_cascada(conexion) -> None:
    conversacion_id = mod.crear_conversacion(conexion)
    sesion = SesionAgente()
    mod.guardar_turno(conexion, conversacion_id, sesion, "hola", "hola!")
    conexion.commit()

    mod.eliminar_conversacion(conexion, conversacion_id)
    conexion.commit()

    assert mod.cargar_conversacion(conexion, conversacion_id) is None
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM mensaje WHERE conversacion_id = %s;", (conversacion_id,)
        )
        (cantidad,) = cursor.fetchone()
    assert cantidad == 0


def test_esquema_version_desactualizada_degrada_sin_romper(conexion) -> None:
    conversacion_id = mod.crear_conversacion(conexion)
    with conexion.cursor() as cursor:
        cursor.execute(
            "UPDATE conversacion SET esquema_version = 999, sesion = %s WHERE id = %s;",
            ('{"estado": {"destino": "Cancun"}}', conversacion_id),
        )
    conexion.commit()

    sesion = mod.cargar_conversacion(conexion, conversacion_id)

    assert sesion is not None
    assert sesion.estado.destino is None
