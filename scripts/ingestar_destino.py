"""CLI de ingesta para un destino piloto.

Uso: python -m scripts.ingestar_destino --destino Salta --lat -24.789 --lon -65.41 --radio 8000

No corre solo: necesita OPENTRIPMAP_API_KEY en el entorno y coordenadas
concretas del destino (no sirve un continente o una region, ver
docs/DECISIONES.md sobre los destinos piloto). Guarda crudo en data/raw/,
normaliza, y deja los documentos listos para cargar_vectores en Fase 2.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from asistente_viajes.ingesta.normalizar import normalizar_poi_opentripmap
from asistente_viajes.ingesta.opentripmap import ErrorOpenTripMap, ingerir_destino

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# Ver fuentes-datos.md: atractivos e historic/museums/natural/cultural/architecture,
# comercios en foods/shops/marketplaces.
KINDS_A_TRAER = [
    "historic",
    "museums",
    "natural",
    "cultural",
    "architecture",
    "foods",
    "shops",
    "marketplaces",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--radio", type=int, default=8000, help="radio en metros")
    parser.add_argument("--limite", type=int, default=200, help="maximo de POIs por busqueda")
    parser.add_argument(
        "--rate",
        default=None,
        help=(
            "filtro de significancia de OpenTripMap ('1','2','3','h'). Util para atractivos "
            "en zonas con mucho comercio chico sin texto de Wikipedia (ver estado.md, "
            "hallazgo de Cancun); no ayuda para comercios."
        ),
    )
    argumentos = parser.parse_args()

    api_key = os.environ.get("OPENTRIPMAP_API_KEY")
    if not api_key:
        logger.error("falta OPENTRIPMAP_API_KEY en el entorno")
        return 1

    try:
        detalles = ingerir_destino(
            destino=argumentos.destino,
            lat=argumentos.lat,
            lon=argumentos.lon,
            radio_metros=argumentos.radio,
            api_key=api_key,
            directorio_raw=DIRECTORIO_RAW,
            kinds=KINDS_A_TRAER,
            limite=argumentos.limite,
            rate=argumentos.rate,
        )
    except ErrorOpenTripMap as error:
        logger.error("no se pudo ingerir %s y no hay cache previa: %s", argumentos.destino, error)
        return 1

    documentos = [
        documento
        for detalle in detalles
        if (documento := normalizar_poi_opentripmap(detalle, destino=argumentos.destino))
        is not None
    ]

    atractivos = sum(1 for d in documentos if d.corpus == "atractivos")
    comercios = sum(1 for d in documentos if d.corpus == "comercios")
    descartados = len(detalles) - len(documentos)

    logger.info(
        "%s: %s atractivos, %s comercios, %s descartados por texto insuficiente o kind desconocido",
        argumentos.destino,
        atractivos,
        comercios,
        descartados,
    )
    logger.info("documentos listos para cargar_vectores (Fase 2), no se persistieron todavia")

    return 0


if __name__ == "__main__":
    sys.exit(main())
