"""Conexion y helpers de Postgres. Un solo punto de entrada a psycopg
para el resto del paquete, asi la connection string vive solo en config.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from asistente_viajes.config import cargar_configuracion


@contextmanager
def obtener_conexion() -> Iterator[psycopg.Connection]:
    """Context manager sobre una conexion nueva, con commit automatico al
    salir sin excepcion y rollback si algo falla."""
    configuracion = cargar_configuracion()
    conexion = psycopg.connect(configuracion.database_url)
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
