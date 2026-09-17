"""Aplica todos los sql/*.sql contra DATABASE_URL, en orden por nombre de
archivo (001_, 002_, ...). Idempotente (CREATE TABLE/INDEX IF NOT EXISTS,
ALTER TABLE ADD COLUMN IF NOT EXISTS).

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

DIRECTORIO_SQL = Path(__file__).resolve().parent.parent / "sql"


def main() -> int:
    try:
        configuracion = cargar_configuracion()
    except ConfiguracionInvalida as error:
        logger.error(str(error))
        return 1

    archivos = sorted(DIRECTORIO_SQL.glob("*.sql"))
    if not archivos:
        logger.error("no hay archivos .sql en %s", DIRECTORIO_SQL)
        return 1

    with psycopg.connect(configuracion.database_url) as conexion:
        for archivo in archivos:
            with conexion.cursor() as cursor:
                cursor.execute(archivo.read_text(encoding="utf-8"))
            conexion.commit()
            logger.info("aplicado %s", archivo.name)

    logger.info("esquema aplicado correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
