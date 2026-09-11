"""Adaptador de Fly Scraper (RapidAPI). Reducido a un solo endpoint.

De todos los endpoints que anuncia el playground para esta API
(auto-complete, search-oneway, search-roundtrip, get-airports,
search-everywhere), **ninguno respondio con datos reales**: el proxy de
RapidAPI devuelve 404 para todos ellos con esta suscripcion, como si no
estuvieran registrados del lado del backend (ver
migracion-amadeus-a-rapidapi.md, addendum de hallazgos 2026-09-10). El
unico que funciona de verdad es `price-calendar`.

Por eso Fly Scraper **no es fuente de `buscar_vuelos`** (eso lo cubre
`booking.py` por si solo) y esta funcion es solo un dato complementario
opcional: precio minimo por dia, util para mostrar "mejor dia para
viajar" en la demo, no para armar una tool de RF7.
"""

from __future__ import annotations

from typing import Any

import psycopg
from pydantic import BaseModel

from asistente_viajes.config import cargar_configuracion
from asistente_viajes.services.rapidapi import client

PROVEEDOR = "fly_scraper"
ENDPOINT_PRICE_CALENDAR = "v2/flights/price-calendar"


class PrecioPorDia(BaseModel):
    dia: str
    precio: float | None = None
    moneda: str | None = None
    aerolinea: str | None = None
    es_fixture: bool = False


def _a_precio_por_dia(registro: dict[str, Any]) -> PrecioPorDia:
    return PrecioPorDia(
        dia=registro.get("day", ""),
        precio=registro.get("price"),
        moneda=registro.get("currency"),
        aerolinea=registro.get("airline"),
    )


def calendario_precios(
    conexion: psycopg.Connection, origen_sky_id: str, destino_sky_id: str
) -> list[PrecioPorDia]:
    """Precio minimo por dia entre dos codigos tipo IATA (`originSkyId`,
    `destinationSkyId`), confirmado con llamadas reales que acepta el
    codigo IATA directo, sin resolucion previa. Dato complementario, no
    reemplaza a `buscar_vuelos` de `booking.py`."""
    configuracion = cargar_configuracion()
    try:
        body = client.llamar(
            conexion,
            PROVEEDOR,
            configuracion.rapidapi_host_fly_scraper,
            ENDPOINT_PRICE_CALENDAR,
            {"originSkyId": origen_sky_id, "destinationSkyId": destino_sky_id},
        )
        if body.get("status") is not True:
            raise client.ErrorRapidAPI(f"Fly Scraper respondio status=false: {body}")
        registros = body.get("data") or []
        return [_a_precio_por_dia(registro) for registro in registros]
    except client.ErrorRapidAPI:
        body = client.leer_fixture(PROVEEDOR, ENDPOINT_PRICE_CALENDAR)
        resultado = [_a_precio_por_dia(registro) for registro in body.get("data") or []]
        for item in resultado:
            item.es_fixture = True
        return resultado
