"""Tool: info_destino (RF8, extension). Clima en vivo mas idioma y moneda.

Se dispara automaticamente al confirmarse el destino (RF12, unica
excepcion a que el orquestador decida solo), no espera que el usuario
pregunte. El clima NO es RAG: es una llamada en vivo a Open-Meteo, gratis y
sin API key, porque es un dato que cambia todo el tiempo. Idioma y moneda
tampoco son RAG: es un dato estructurado casi fijo, alcanza con la tabla de
referencia (ver fuentes-datos.md, por que aca no hace falta RAG ni
embeddings).

Limitacion real de Open-Meteo: el pronostico solo llega a unos 16 dias.
Para fechas mas lejanas se devuelve la limitacion explicita, nunca un
pronostico inventado.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HORIZONTE_PRONOSTICO_DIAS = 16
TIMEOUT_SEGUNDOS = 10.0

RUTA_PAISES = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "reference" / "paises.json"
)


class InfoClima(BaseModel):
    disponible: bool
    detalle: str
    temperatura_maxima: list[float] | None = None
    temperatura_minima: list[float] | None = None
    precipitacion_mm: list[float] | None = None


class InfoIdiomaMoneda(BaseModel):
    idioma: str | None
    moneda: str | None


class InfoDestino(BaseModel):
    destino: str
    clima: InfoClima
    idioma_moneda: InfoIdiomaMoneda


def _resumir_pronostico(
    temperatura_maxima: list[float], temperatura_minima: list[float], precipitacion_mm: list[float]
) -> str:
    """Une los arrays diarios en una sola linea legible, con numeros
    reales (antes se mostraba solo un "pronostico en vivo" generico y las
    temperaturas nunca llegaban al usuario, aunque ya se pedian a la
    API)."""
    maxima = max(temperatura_maxima)
    minima = min(temperatura_minima)
    dias_con_lluvia = sum(1 for mm in precipitacion_mm if mm > 0)
    detalle = f"Temperatura prevista entre {minima:.0f}°C y {maxima:.0f}°C."
    if dias_con_lluvia:
        detalle += f" Lluvia estimada en {dias_con_lluvia} de {len(precipitacion_mm)} día(s)."
    return detalle


def obtener_clima(
    lat: float, lon: float, fecha_inicio: date, fecha_fin: date, hoy: date | None = None
) -> InfoClima:
    """Pronostico en vivo si las fechas caen dentro del horizonte de la
    fuente (~16 dias). Fuera de ese horizonte, devuelve la limitacion
    explicita en vez de inventar un numero. Textos en tono de asesor de
    viajes: no nombran al proveedor ni exponen texto crudo de excepcion
    (eso queda en el log, no en la respuesta al cliente)."""
    hoy = hoy or datetime.now(tz=UTC).date()
    limite = hoy + timedelta(days=HORIZONTE_PRONOSTICO_DIAS)

    if fecha_inicio > limite:
        return InfoClima(
            disponible=False,
            detalle=(
                f"Todavía no tengo pronóstico confiable para esas fechas (el clima en vivo solo "
                f"llega hasta {HORIZONTE_PRONOSTICO_DIAS} días por delante); más cerca del viaje "
                f"puedo consultarlo de nuevo."
            ),
        )

    parametros = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
        "start_date": fecha_inicio.isoformat(),
        "end_date": min(fecha_fin, limite).isoformat(),
    }

    try:
        respuesta = httpx.get(URL_OPEN_METEO, params=parametros, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPError as error:
        logger.warning("fallo la consulta de clima en vivo: %s", error)
        return InfoClima(disponible=False, detalle="No pude consultar el clima en este momento.")

    diario = datos.get("daily", {})
    temperatura_maxima = diario.get("temperature_2m_max") or []
    temperatura_minima = diario.get("temperature_2m_min") or []
    precipitacion_mm = diario.get("precipitation_sum") or []

    if not (temperatura_maxima and temperatura_minima):
        return InfoClima(disponible=False, detalle="No pude consultar el clima en este momento.")

    return InfoClima(
        disponible=True,
        detalle=_resumir_pronostico(temperatura_maxima, temperatura_minima, precipitacion_mm),
        temperatura_maxima=temperatura_maxima,
        temperatura_minima=temperatura_minima,
        precipitacion_mm=precipitacion_mm,
    )


def obtener_idioma_moneda(pais: str, ruta_paises: Path = RUTA_PAISES) -> InfoIdiomaMoneda:
    """Lee la tabla de referencia pais -> idioma -> moneda. No es RAG ni
    necesita LLM, es un diccionario chico que casi no cambia."""
    datos = json.loads(ruta_paises.read_text(encoding="utf-8"))
    registro = datos.get(pais)

    if registro is None and pais:
        # D-23: un destino ingerido bajo demanda trae el pais como codigo
        # ISO-2 (lo que devuelve el geocoder), no como nombre en espanol.
        codigo = pais.strip().upper()
        registro = next(
            (
                valor
                for clave, valor in datos.items()
                if not clave.startswith("_") and valor.get("iso") == codigo
            ),
            None,
        )

    if registro is None:
        logger.warning("pais sin entrada en paises.json: %s", pais)
        return InfoIdiomaMoneda(idioma=None, moneda=None)
    return InfoIdiomaMoneda(idioma=registro.get("idioma"), moneda=registro.get("moneda"))


def info_destino(
    destino: str,
    pais: str,
    lat: float,
    lon: float,
    fecha_inicio: date,
    fecha_fin: date,
) -> InfoDestino:
    """Combina clima en vivo e idioma/moneda de referencia para un destino
    ya confirmado. Se llama automaticamente al confirmarse el destino
    (RF12), no es una decision del agente."""
    return InfoDestino(
        destino=destino,
        clima=obtener_clima(lat, lon, fecha_inicio, fecha_fin),
        idioma_moneda=obtener_idioma_moneda(pais),
    )
