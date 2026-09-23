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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

URL_BASE = "https://api.opentripmap.com/0.1/en/places"
TIMEOUT_SEGUNDOS = 15.0

# Cuantos detalles de POI se piden en paralelo (ver ingerir_destino). Con 8
# workers OpenTripMap empieza a contestar 429 y se pierden POIs (medido
# ingiriendo Tokio: 21 atractivos en vez de los ~40 esperables).
WORKERS_DETALLE = 4
REINTENTOS_POR_RATE_LIMIT = 2
ESPERA_TRAS_RATE_LIMIT_SEGUNDOS = 1.5


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
    rate: str | None = None,
) -> list[dict[str, Any]]:
    """Paso 1: lista liviana de POIs alrededor de un punto. Sin texto.

    `rate` filtra por significancia segun OpenTripMap ('1', '2', '3', 'h',
    de menor a mayor). Sin esto, el radius search devuelve los primeros
    `limite` resultados sin priorizar por relevancia, y en zonas con mucho
    comercio chico (ej. Cancun) eso llena el limite de comercios sin texto
    de Wikipedia antes de llegar a los atractivos genuinos. Util para el
    corpus de atractivos; para comercios no ayuda porque casi nunca tienen
    rate alto (ver estado.md, hallazgo de la ingesta real de Cancun)."""
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
    if rate:
        parametros["rate"] = rate

    try:
        respuesta = httpx.get(f"{URL_BASE}/radius", params=parametros, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        return respuesta.json()
    except httpx.HTTPError as error:
        raise ErrorOpenTripMap(f"fallo la busqueda por radio: {error}") from error


def geolocalizar(api_key: str, nombre: str) -> dict[str, Any] | None:
    """Paso 0 (Fase 7E, D-23): resuelve el nombre de una ciudad a
    coordenadas y pais, para poder ingerir un destino que no estaba
    precargado. Devuelve None si OpenTripMap no reconoce el lugar, que es
    justamente como se distingue "un destino que todavia no tenemos" de
    "un lugar que no existe".

    Este endpoint es el que habilita que el asistente responda por
    cualquier destino y no solo por una lista fija (ver destinos.py,
    asegurar_destino)."""
    try:
        respuesta = httpx.get(
            f"{URL_BASE}/geoname",
            params={"name": nombre, "apikey": api_key},
            timeout=TIMEOUT_SEGUNDOS,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPError as error:
        raise ErrorOpenTripMap(f"fallo geoname para '{nombre}': {error}") from error

    # La API contesta 200 con status "NOT_FOUND" en vez de un 404.
    if not datos or datos.get("status") == "NOT_FOUND" or datos.get("lat") is None:
        return None
    return datos


def obtener_detalle(api_key: str, xid: str) -> dict[str, Any]:
    """Paso 2: detalle de un POI puntual, incluye el extracto de Wikipedia
    si existe.

    Reintenta ante 429: pidiendo detalles en paralelo (ver ingerir_destino)
    el rate limit aparece seguido, y un 429 sin reintento no es un error
    del POI, es simplemente haber preguntado demasiado rapido. Sin esto se
    perdian POIs reales y el corpus del destino quedaba mas pobre de lo
    que la fuente en verdad tiene."""
    for intento in range(REINTENTOS_POR_RATE_LIMIT + 1):
        try:
            respuesta = httpx.get(
                f"{URL_BASE}/xid/{xid}",
                params={"apikey": api_key},
                timeout=TIMEOUT_SEGUNDOS,
            )
            respuesta.raise_for_status()
            return respuesta.json()
        except httpx.HTTPStatusError as error:
            es_ultimo = intento == REINTENTOS_POR_RATE_LIMIT
            if error.response.status_code != 429 or es_ultimo:
                raise ErrorOpenTripMap(f"fallo el detalle de xid={xid}: {error}") from error
            time.sleep(ESPERA_TRAS_RATE_LIMIT_SEGUNDOS * (intento + 1))
        except httpx.HTTPError as error:
            raise ErrorOpenTripMap(f"fallo el detalle de xid={xid}: {error}") from error

    raise ErrorOpenTripMap(f"fallo el detalle de xid={xid}: rate limit persistente")


def ingerir_destino(
    destino: str,
    lat: float,
    lon: float,
    radio_metros: int,
    api_key: str,
    directorio_raw: Path,
    kinds: list[str] | None = None,
    limite: int = 200,
    rate: str | None = None,
) -> list[dict[str, Any]]:
    """Corre los dos pasos para un destino y persiste las respuestas crudas
    en directorio_raw. Si la API falla en cualquier paso, intenta recuperar
    lo ya guardado de una corrida anterior y avisa, no rompe el pipeline.
    """
    directorio_raw.mkdir(parents=True, exist_ok=True)
    ruta_lista = _ruta_cruda(directorio_raw, destino, "lista")
    ruta_detalles = _ruta_cruda(directorio_raw, destino, "detalles")

    try:
        lista = buscar_por_radio(
            api_key, lat, lon, radio_metros, kinds=kinds, limite=limite, rate=rate
        )
        ruta_lista.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")
    except ErrorOpenTripMap as error:
        logger.warning(
            "busqueda por radio fallo para %s (%s), usando cache si existe", destino, error
        )
        if not ruta_lista.exists():
            raise
        lista = json.loads(ruta_lista.read_text(encoding="utf-8"))

    # El paso 2 es una llamada por POI y son independientes entre si: en
    # serie, ingerir un destino tarda minutos, y desde D-23 esto corre
    # DENTRO de un turno de chat (la primera vez que alguien nombra una
    # ciudad nueva), asi que el cliente esperaria mirando un spinner. En
    # paralelo baja a segundos. El limite de workers es deliberadamente
    # bajo para no gatillar el rate limit de OpenTripMap.
    xids = [poi["xid"] for poi in lista if poi.get("xid")]
    detalles: list[dict[str, Any]] = []
    fallo_alguno = False

    if xids:
        with ThreadPoolExecutor(max_workers=WORKERS_DETALLE) as ejecutor:
            futuros = {ejecutor.submit(obtener_detalle, api_key, xid): xid for xid in xids}
            for futuro in as_completed(futuros):
                try:
                    detalles.append(futuro.result())
                except ErrorOpenTripMap as error:
                    fallo_alguno = True
                    logger.warning("no se pudo obtener detalle de %s: %s", futuros[futuro], error)

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
