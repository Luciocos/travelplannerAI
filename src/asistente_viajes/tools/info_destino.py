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


def obtener_clima(
    lat: float, lon: float, fecha_inicio: date, fecha_fin: date, hoy: date | None = None
) -> InfoClima:
    """Pronostico en vivo si las fechas caen dentro del horizonte de
    Open-Meteo (~16 dias). Fuera de ese horizonte, devuelve la limitacion
    explicita en vez de inventar un numero."""
    hoy = hoy or datetime.now(tz=UTC).date()
    limite = hoy + timedelta(days=HORIZONTE_PRONOSTICO_DIAS)

    if fecha_inicio > limite:
        return InfoClima(
            disponible=False,
            detalle=(
                f"El pronostico de Open-Meteo solo cubre los proximos "
                f"{HORIZONTE_PRONOSTICO_DIAS} dias. Para fechas mas lejanas no hay dato "
                f"en vivo confiable, se aclara en vez de inventar un numero."
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
        logger.warning("Open-Meteo no respondio: %s", error)
        return InfoClima(disponible=False, detalle=f"No se pudo consultar el clima ahora: {error}")

    diario = datos.get("daily", {})
    return InfoClima(
        disponible=True,
        detalle="Pronostico en vivo de Open-Meteo.",
        temperatura_maxima=diario.get("temperature_2m_max"),
        temperatura_minima=diario.get("temperature_2m_min"),
        precipitacion_mm=diario.get("precipitation_sum"),
    )


def obtener_idioma_moneda(pais: str, ruta_paises: Path = RUTA_PAISES) -> InfoIdiomaMoneda:
    """Lee la tabla de referencia pais -> idioma -> moneda. No es RAG ni
    necesita LLM, es un diccionario chico que casi no cambia."""
    datos = json.loads(ruta_paises.read_text(encoding="utf-8"))
    registro = datos.get(pais)
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
