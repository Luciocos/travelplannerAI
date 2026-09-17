"""Carga (o recarga) los 3 destinos piloto de punta a punta en pgvector.

Uso: python -m scripts.cargar_todos [--reemplazar]

--reemplazar borra primero las filas de documento_rag de cada destino
piloto antes de volver a cargarlo. Hace falta para que un cambio en las
reglas de normalizacion (por ejemplo, excluir un kind que antes se
aceptaba, ver P-08 en DIFICULTADES.md) se refleje de verdad: el upsert
por xid actualiza o agrega filas, pero nunca borra una fila cuyo xid ya
no se genera en esta corrida.
"""

from __future__ import annotations

import argparse
import logging
import sys

from asistente_viajes.db import obtener_conexion
from asistente_viajes.destinos import cargar_destinos_piloto
from asistente_viajes.ingesta.cargar_vectores import cargar_documentos
from scripts.cargar_destino import documentos_de_destino

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQL_BORRAR_DESTINO = (
    "DELETE FROM documento_rag WHERE lower(unaccent(destino)) = lower(unaccent(%(destino)s));"
)


def _borrar_destino(destino: str) -> int:
    with obtener_conexion() as conexion, conexion.cursor() as cursor:
        cursor.execute(SQL_BORRAR_DESTINO, {"destino": destino})
        return cursor.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reemplazar",
        action="store_true",
        help="borra las filas existentes de cada destino antes de recargarlo",
    )
    argumentos = parser.parse_args()

    destinos = sorted(cargar_destinos_piloto().keys())
    total = 0
    for destino in destinos:
        if argumentos.reemplazar:
            borradas = _borrar_destino(destino)
            logger.info("%s: %s filas viejas borradas", destino, borradas)

        documentos = documentos_de_destino(destino)
        if not documentos:
            logger.error("%s: no hay documentos para cargar (ni opentripmap ni curados)", destino)
            continue

        cantidad = cargar_documentos(documentos)
        total += cantidad
        logger.info("%s: %s documentos cargados", destino, cantidad)

    logger.info("total: %s documentos cargados en %s destinos", total, len(destinos))
    return 0


if __name__ == "__main__":
    sys.exit(main())
