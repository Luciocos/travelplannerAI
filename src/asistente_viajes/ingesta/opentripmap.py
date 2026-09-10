"""Cliente de OpenTripMap en dos pasos (ver fuentes-datos.md, es central y
no hay que saltearlo):

1. Busqueda por radio, devuelve una lista liviana (nombre, xid, kind,
   coordenadas), sin texto descriptivo.
2. Detalle por xid, trae direccion, imagen y el extracto de Wikipedia
   cuando existe. Eso es lo que se embebe, nunca el nombre pelado.

La respuesta cruda de ambos pasos se guarda en data/raw/ antes de normalizar,
para no depender de la API en cada corrida ni quemar cuota (5.000 req/dia).
Si la API falla, se loguea y se sigue con lo que ya haya en data/raw/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL_BASE = "https://api.opentripmap.com/0.1/en/places"
TIMEOUT_SEGUNDOS = 15.0


class ErrorOpenTripMap(RuntimeError):
    """La API no respondio o respondio con error. No tiene que voltear el pipeline."""


def _ruta_cruda(directorio_raw: Path, destino: str, sufijo: str) -> Path:
    nombre_archivo = f"{destino.lower().replace(' ', '_')}_{sufijo}.json"
    return directorio_raw / nombre_archivo


def buscar_por_radio(
    api_key: str,
    lat: float,
    lon: float,
    radio_metros: int,
    kinds: list[str] | None = None,
    limite: int = 200,
) -> list[dict[str, Any]]:
    """Paso 1: lista liviana de POIs alrededor de un punto. Sin texto."""
    parametros: dict[str, Any] = {
        "radius": radio_metros,
        "lat": lat,
        "lon": lon,
        "limit": limite,
        "apikey": api_key,
        "format": "json",
    }
    if kinds:
        parametros["kinds"] = ",".join(kinds)

    try:
        respuesta = httpx.get(f"{URL_BASE}/radius", params=parametros, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        return respuesta.json()
    except httpx.HTTPError as error:
        raise ErrorOpenTripMap(f"fallo la busqueda por radio: {error}") from error


def obtener_detalle(api_key: str, xid: str) -> dict[str, Any]:
    """Paso 2: detalle de un POI puntual, incluye el extracto de Wikipedia si existe."""
    try:
        respuesta = httpx.get(
            f"{URL_BASE}/xid/{xid}",
            params={"apikey": api_key},
            timeout=TIMEOUT_SEGUNDOS,
        )
        respuesta.raise_for_status()
        return respuesta.json()
    except httpx.HTTPError as error:
        raise ErrorOpenTripMap(f"fallo el detalle de xid={xid}: {error}") from error


def ingerir_destino(
    destino: str,
    lat: float,
    lon: float,
    radio_metros: int,
    api_key: str,
    directorio_raw: Path,
    kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Corre los dos pasos para un destino y persiste las respuestas crudas
    en directorio_raw. Si la API falla en cualquier paso, intenta recuperar
    lo ya guardado de una corrida anterior y avisa, no rompe el pipeline.
    """
    directorio_raw.mkdir(parents=True, exist_ok=True)
    ruta_lista = _ruta_cruda(directorio_raw, destino, "lista")
    ruta_detalles = _ruta_cruda(directorio_raw, destino, "detalles")

    try:
        lista = buscar_por_radio(api_key, lat, lon, radio_metros, kinds=kinds)
        ruta_lista.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    except ErrorOpenTripMap as error:
        logger.warning(
            "busqueda por radio fallo para %s (%s), usando cache si existe", destino, error
        )
        if not ruta_lista.exists():
            raise
        lista = json.loads(ruta_lista.read_text(encoding="utf-8"))

    detalles: list[dict[str, Any]] = []
    fallo_alguno = False
    for poi in lista:
        xid = poi.get("xid")
        if not xid:
            continue
        try:
            detalle = obtener_detalle(api_key, xid)
            detalles.append(detalle)
        except ErrorOpenTripMap as error:
            fallo_alguno = True
            logger.warning("no se pudo obtener detalle de %s: %s", xid, error)

    if detalles:
        ruta_detalles.write_text(
            json.dumps(detalles, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif ruta_detalles.exists():
        logger.warning("sin detalles nuevos para %s, usando cache existente", destino)
        detalles = json.loads(ruta_detalles.read_text(encoding="utf-8"))

    if fallo_alguno:
        logger.warning("la ingesta de %s termino con errores parciales, revisar logs", destino)

    return detalles
