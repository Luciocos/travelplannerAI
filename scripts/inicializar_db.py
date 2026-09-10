"""Aplica sql/001_schema.sql contra DATABASE_URL. Idempotente (usa
CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).

Uso: python -m scripts.inicializar_db
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import psycopg

from asistente_viajes.config import ConfiguracionInvalida, cargar_configuracion

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RUTA_ESQUEMA = Path(__file__).resolve().parent.parent / "sql" / "001_schema.sql"


def main() -> int:
    try:
        configuracion = cargar_configuracion()
    except ConfiguracionInvalida as error:
        logger.error(str(error))
        return 1

    sql = RUTA_ESQUEMA.read_text(encoding="utf-8")

    with psycopg.connect(configuracion.database_url) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql)
        conexion.commit()

    logger.info("esquema aplicado correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
