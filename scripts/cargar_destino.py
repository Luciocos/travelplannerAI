"""Combina lo ingerido de OpenTripMap (data/raw) y lo curado a mano
(data/curated) para un destino, y lo carga a pgvector (Fase 2).

Uso: python -m scripts.cargar_destino --destino Cancun
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from asistente_viajes.ingesta.cargar_vectores import cargar_documentos
from asistente_viajes.ingesta.normalizar import (
    DocumentoCorpus,
    deduplicar_documentos,
    normalizar_curado,
    normalizar_poi_opentripmap,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DIRECTORIO_CURATED = Path(__file__).resolve().parent.parent / "data" / "curated"


def _documentos_de_opentripmap(destino: str, directorio_raw: Path) -> list[DocumentoCorpus]:
    ruta = directorio_raw / f"{destino.lower().replace(' ', '_')}_detalles.json"
    if not ruta.exists():
        logger.warning("no hay data/raw/%s para %s, se omite", ruta.name, destino)
        return []
    detalles = json.loads(ruta.read_text(encoding="utf-8"))
    normalizados = (normalizar_poi_opentripmap(detalle, destino=destino) for detalle in detalles)
    return [documento for documento in normalizados if documento is not None]


def _documentos_curados(destino: str, directorio_curated: Path) -> list[DocumentoCorpus]:
    """Lee todos los .json de data/curated/ y se queda con los registros
    del destino pedido. No importa el nombre del archivo, se filtra por el
    campo 'destino' de cada registro."""
    documentos: list[DocumentoCorpus] = []
    for ruta in sorted(directorio_curated.glob("*.json")):
        registros = json.loads(ruta.read_text(encoding="utf-8"))
        for registro in registros:
            if registro.get("destino", "").lower() == destino.lower():
                documentos.append(normalizar_curado(registro))
    return documentos


def documentos_de_destino(
    destino: str,
    directorio_raw: Path = DIRECTORIO_RAW,
    directorio_curated: Path = DIRECTORIO_CURATED,
) -> list[DocumentoCorpus]:
    """OpenTripMap + curados de un destino, deduplicados por nombre (ver
    P-08 en DIFICULTADES.md). Punto unico que reusa tambien
    scripts/cargar_todos.py."""
    documentos = _documentos_de_opentripmap(destino, directorio_raw) + _documentos_curados(
        destino, directorio_curated
    )
    return deduplicar_documentos(documentos)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", required=True)
    argumentos = parser.parse_args()

    documentos = documentos_de_destino(argumentos.destino, DIRECTORIO_RAW, DIRECTORIO_CURATED)

    if not documentos:
        logger.error("no hay documentos para cargar para %s", argumentos.destino)
        return 1

    atractivos = sum(1 for documento in documentos if documento.corpus == "atractivos")
    comercios = sum(1 for documento in documentos if documento.corpus == "comercios")
    logger.info(
        "%s: %s atractivos, %s comercios a cargar (opentripmap + curados)",
        argumentos.destino,
        atractivos,
        comercios,
    )

    cantidad = cargar_documentos(documentos)
    logger.info("cargados %s documentos en total en documento_rag", cantidad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
