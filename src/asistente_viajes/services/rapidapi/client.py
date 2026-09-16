"""Cliente HTTP compartido para RapidAPI (Booking.com15, Fly Scraper).

Punto unico por el que pasan todas las llamadas a los dos proveedores:
headers, timeout, retry, contador de cuota persistido y modo fixtures.
Ver migracion-amadeus-a-rapidapi.md, seccion 3.1 y 5.

Lo que este modulo NO sabe: la forma de la respuesta de cada proveedor
(eso es de `booking.py`/`fly_scraper.py`) ni cual es el proveedor de
fallback de otro (eso es de las tools, seccion 4.3 del documento).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psycopg

from asistente_viajes.config import cargar_configuracion

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 15.0
MAXIMO_REINTENTOS = 2
CODIGOS_REINTENTABLES = {429, 500, 502, 503, 504}
UMBRAL_ALERTA_CUOTA = 0.8

RUTA_FIXTURES = Path(__file__).resolve().parent / "fixtures"

SQL_CONTADOR_ACTUAL = """
SELECT cantidad FROM uso_api_mensual WHERE proveedor = %(proveedor)s AND periodo = %(periodo)s;
"""

SQL_INCREMENTAR_CONTADOR = """
INSERT INTO uso_api_mensual (proveedor, periodo, cantidad)
VALUES (%(proveedor)s, %(periodo)s, 1)
ON CONFLICT (proveedor, periodo) DO UPDATE SET cantidad = uso_api_mensual.cantidad + 1
RETURNING cantidad;
"""


class ErrorRapidAPI(RuntimeError):
    """La llamada fallo (red o HTTP no reintentable) y no hay fixture de
    respaldo cargado. La tool decide si intenta el proveedor de fallback."""


class ErrorCuotaAgotada(ErrorRapidAPI):
    """429 persistente tras los reintentos, o guard local al 100% de la
    cuota mensual. Senial explicita para que la tool active el fallback
    cruzado antes de resignarse a un fixture."""


def _periodo_actual() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m")


def _nombre_fixture(proveedor: str, endpoint: str) -> str:
    limpio = endpoint.strip("/").replace("/", "_")
    return f"{proveedor}_{limpio}.json"


def leer_fixture(proveedor: str, endpoint: str) -> dict[str, Any]:
    ruta = RUTA_FIXTURES / _nombre_fixture(proveedor, endpoint)
    if not ruta.exists():
        raise ErrorRapidAPI(f"no hay fixture para {proveedor} {endpoint} en {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar_fixture(proveedor: str, endpoint: str, datos: dict[str, Any]) -> Path:
    """Graba una respuesta real como fixture. Uso manual durante la
    verificacion de cada endpoint (seccion 4/6 del documento de
    migracion), nunca se llama desde el camino normal de ejecucion."""
    RUTA_FIXTURES.mkdir(parents=True, exist_ok=True)
    ruta = RUTA_FIXTURES / _nombre_fixture(proveedor, endpoint)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def contador_actual(conexion: psycopg.Connection, proveedor: str) -> int:
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CONTADOR_ACTUAL, {"proveedor": proveedor, "periodo": _periodo_actual()})
        fila = cursor.fetchone()
    return fila[0] if fila else 0


def _incrementar_contador(conexion: psycopg.Connection, proveedor: str) -> int:
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_INCREMENTAR_CONTADOR, {"proveedor": proveedor, "periodo": _periodo_actual()}
        )
        (cantidad,) = cursor.fetchone()
    return cantidad


def _dormir(segundos: float) -> None:
    time.sleep(segundos)


def llamar(
    conexion: psycopg.Connection,
    proveedor: str,
    host: str,
    endpoint: str,
    parametros: dict[str, Any],
) -> dict[str, Any]:
    """Llama a `endpoint` en `host` con `parametros`, o sirve el fixture
    correspondiente si `USE_FIXTURES=true` o si la cuota mensual local ya
    esta al 100%. Devuelve el body crudo, sin interpretar el envelope del
    proveedor (eso es responsabilidad de cada adaptador).

    Levanta `ErrorCuotaAgotada` si un 429 persiste tras los reintentos, y
    `ErrorRapidAPI` para cualquier otro fallo sin fixture de respaldo. La
    tool que llama decide si eso dispara el fallback cruzado."""
    configuracion = cargar_configuracion()

    if configuracion.usar_fixtures:
        logger.info("USE_FIXTURES=true, sirviendo fixture de %s %s", proveedor, endpoint)
        return leer_fixture(proveedor, endpoint)

    cuota = _cuota_configurada(configuracion, proveedor)
    usadas = contador_actual(conexion, proveedor)
    if cuota and usadas >= cuota:
        logger.warning(
            "cuota mensual de %s agotada (%s/%s), sirviendo fixture sin llamar a la red",
            proveedor,
            usadas,
            cuota,
        )
        return leer_fixture(proveedor, endpoint)
    if cuota and usadas >= cuota * UMBRAL_ALERTA_CUOTA:
        logger.warning(
            "cuota de %s al %s%% o mas (%s/%s)",
            proveedor,
            int(UMBRAL_ALERTA_CUOTA * 100),
            usadas,
            cuota,
        )

    url = f"https://{host}/{endpoint.lstrip('/')}"
    headers = {"x-rapidapi-key": configuracion.rapidapi_key or "", "x-rapidapi-host": host}

    intento = 0
    while True:
        inicio = time.monotonic()
        try:
            respuesta = httpx.get(url, headers=headers, params=parametros, timeout=TIMEOUT_SEGUNDOS)
        except httpx.HTTPError as error:
            logger.warning("error de red llamando a %s %s: %s", proveedor, endpoint, error)
            raise ErrorRapidAPI(f"{proveedor} {endpoint}: error de red") from error

        latencia_ms = (time.monotonic() - inicio) * 1000
        logger.info(
            "%s %s -> %s en %.0fms (intento %s)",
            proveedor,
            endpoint,
            respuesta.status_code,
            latencia_ms,
            intento + 1,
        )
        _incrementar_contador(conexion, proveedor)

        if respuesta.status_code not in CODIGOS_REINTENTABLES:
            break
        if intento >= MAXIMO_REINTENTOS:
            break
        intento += 1
        _dormir(2**intento)

    if respuesta.status_code == 429:
        logger.warning(
            "429 persistente de %s tras %s intentos, cuota agotada", proveedor, intento + 1
        )
        raise ErrorCuotaAgotada(f"{proveedor} {endpoint}: 429 tras reintentos")

    if respuesta.status_code >= 400:
        raise ErrorRapidAPI(f"{proveedor} {endpoint}: HTTP {respuesta.status_code}")

    return respuesta.json()


def _cuota_configurada(configuracion: Any, proveedor: str) -> int:
    if proveedor == "booking":
        return configuracion.rapidapi_quota_booking
    if proveedor == "fly_scraper":
        return configuracion.rapidapi_quota_fly_scraper
    raise ValueError(f"proveedor desconocido: {proveedor}")
