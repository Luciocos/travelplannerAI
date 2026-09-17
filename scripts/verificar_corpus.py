"""Verifica que el corpus cargado en pgvector cumpla el minimo de Fase 1.

Uso: python -m scripts.verificar_corpus

Imprime destino/corpus/fuente con sus conteos y termina con codigo de
salida 1 si algun destino piloto tiene menos de MINIMO_ATRACTIVOS
atractivos reales (D-07 en DECISIONES.md).
"""

from __future__ import annotations

import logging
import sys
from collections import Counter

from asistente_viajes.db import obtener_conexion
from asistente_viajes.destinos import cargar_destinos_piloto

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MINIMO_ATRACTIVOS = 20

SQL_CONTEOS = """
SELECT destino, corpus, fuente, count(*)
FROM documento_rag
GROUP BY destino, corpus, fuente
ORDER BY destino, corpus, fuente;
"""


def main() -> int:
    destinos_piloto = sorted(cargar_destinos_piloto().keys())

    with obtener_conexion() as conexion, conexion.cursor() as cursor:
        cursor.execute(SQL_CONTEOS)
        filas = cursor.fetchall()

    atractivos_por_destino: Counter[str] = Counter()
    for destino, corpus, fuente, cantidad in filas:
        logger.info("%-10s %-11s %-11s %s", destino, corpus, fuente, cantidad)
        if corpus == "atractivos":
            atractivos_por_destino[destino] += cantidad

    ok = True
    for destino in destinos_piloto:
        cantidad = atractivos_por_destino.get(destino, 0)
        if cantidad < MINIMO_ATRACTIVOS:
            logger.error(
                "%s: %s atractivos, por debajo del minimo (%s)",
                destino,
                cantidad,
                MINIMO_ATRACTIVOS,
            )
            ok = False
        else:
            logger.info("%s: %s atractivos, OK (minimo %s)", destino, cantidad, MINIMO_ATRACTIVOS)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
