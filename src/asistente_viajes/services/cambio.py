"""Conversion de moneda (extension, D-18). Dos fuentes en vivo, las dos
gratis y sin API key:

- **dolarapi.com** para USD -> ARS: da el dolar oficial Y el dolar
  tarjeta (lo que de verdad paga un viajero argentino pagando con
  tarjeta en el exterior), mas relevante para el caso de uso real de
  este TP que un tipo de cambio generico.
- **open.er-api.com** para cualquier otra moneda (EUR, MXN...): se
  actualiza una vez por dia, requiere el credito "Rates By Exchange
  Rate API" en cualquier lugar donde se muestre (ver DECISIONES.md).

Cacheado en memoria del proceso: ninguna de las dos fuentes cambia mas
de una vez por dia, pedirla de nuevo en cada turno de la misma sesion
no aporta nada y arriesga el limite de la fuente gratuita.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

URL_DOLARAPI = "https://dolarapi.com/v1/dolares"
URL_EXCHANGE_RATE = "https://open.er-api.com/v6/latest/USD"
TIMEOUT_SEGUNDOS = 10.0
SEGUNDOS_CACHE = 3600

CREDITO_EXCHANGE_RATE_API = "Rates By Exchange Rate API"


@dataclass
class Cotizacion:
    disponible: bool
    detalle: str
    ars_oficial: float | None = None
    ars_tarjeta: float | None = None


_cache: dict[str, tuple[float, object]] = {}


def _desde_cache_o_pedir(clave: str, pedir):
    entrada = _cache.get(clave)
    ahora = time.monotonic()
    if entrada and ahora - entrada[0] < SEGUNDOS_CACHE:
        return entrada[1]
    valor = pedir()
    _cache[clave] = (ahora, valor)
    return valor


def _pedir_dolares_argentina() -> dict[str, float] | None:
    def _pedir() -> dict[str, float]:
        respuesta = httpx.get(URL_DOLARAPI, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        return {fila["casa"]: fila["venta"] for fila in respuesta.json()}

    try:
        return _desde_cache_o_pedir("dolarapi", _pedir)
    except httpx.HTTPError as error:
        logger.warning("fallo la consulta de dolarapi.com: %s", error)
        return None


def _pedir_tasas_cruzadas() -> dict[str, float] | None:
    def _pedir() -> dict[str, float]:
        respuesta = httpx.get(URL_EXCHANGE_RATE, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        return respuesta.json().get("rates") or {}

    try:
        return _desde_cache_o_pedir("exchangerate", _pedir)
    except httpx.HTTPError as error:
        logger.warning("fallo la consulta de open.er-api.com: %s", error)
        return None


def convertir_desde_usd(monto_usd: float, moneda_destino: str) -> Cotizacion:
    """Convierte un monto en USD (la moneda en la que armar_plan estima
    costos, ver costos.py) a la moneda pedida. ARS por dolarapi.com,
    cualquier otra por open.er-api.com. Nunca inventa una tasa: si la
    fuente no responde o no tiene esa moneda, lo dice explicitamente."""
    moneda_destino = moneda_destino.upper().strip()

    if moneda_destino == "ARS":
        dolares = _pedir_dolares_argentina()
        if not dolares:
            return Cotizacion(
                disponible=False,
                detalle="No pude consultar la cotización del dólar en este momento.",
            )
        oficial = dolares.get("oficial")
        tarjeta = dolares.get("tarjeta")
        if not (oficial or tarjeta):
            return Cotizacion(
                disponible=False,
                detalle="No tengo la cotización del dólar oficial ni tarjeta en este momento.",
            )
        partes = []
        if oficial:
            partes.append(f"USD {monto_usd:.0f} = ARS {monto_usd * oficial:.0f} (dólar oficial)")
        if tarjeta:
            partes.append(
                f"USD {monto_usd:.0f} = ARS {monto_usd * tarjeta:.0f} (dólar tarjeta, el que se paga con tarjeta en el exterior)"
            )
        return Cotizacion(
            disponible=True,
            detalle=". ".join(partes) + ". Cotización de referencia (dolarapi.com), puede variar.",
            ars_oficial=monto_usd * oficial if oficial else None,
            ars_tarjeta=monto_usd * tarjeta if tarjeta else None,
        )

    tasas = _pedir_tasas_cruzadas()
    if not tasas or moneda_destino not in tasas:
        return Cotizacion(
            disponible=False,
            detalle=f"No tengo una cotización confiable para {moneda_destino} en este momento.",
        )
    convertido = monto_usd * tasas[moneda_destino]
    return Cotizacion(
        disponible=True,
        detalle=(
            f"USD {monto_usd:.0f} = {moneda_destino} {convertido:.0f}. "
            f"Cotización de referencia ({CREDITO_EXCHANGE_RATE_API}), puede variar."
        ),
    )
