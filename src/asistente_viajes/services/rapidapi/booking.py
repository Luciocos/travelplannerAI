"""Adaptador de Booking.com15 (RapidAPI) para hoteles (RF6) y vuelos (RF7).

Booking.com15 termino siendo la unica fuente real y viable para los dos
dominios: Fly Scraper, pensado originalmente como primario de vuelos,
resulto no tener funcionando ningun endpoint de busqueda real (ver
migracion-amadeus-a-rapidapi.md, addendum de hallazgos 2026-09-10). Este
modulo es el unico lugar del proyecto que conoce la forma cruda de las
respuestas de Booking.com15.

Dos dominios, mismo host, pero **namespaces de id distintos**: la
resolucion de destino de hoteles (`dest_id` + `search_type`) no es
intercambiable con la de vuelos (`id` + `type`), aunque las dos vengan
del mismo `searchDestination`-como-nombre-de-endpoint. Por eso el cache
de destinos usa proveedores separados: `booking_hoteles` y
`booking_vuelos` (ver cache.py).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import psycopg

from asistente_viajes.config import cargar_configuracion
from asistente_viajes.services.rapidapi import client
from asistente_viajes.services.rapidapi.cache import (
    buscar_destino_cacheado,
    guardar_destino_cacheado,
)
from asistente_viajes.services.rapidapi.models import Alojamiento, DestinoResuelto, OpcionVuelo

logger = logging.getLogger(__name__)

PROVEEDOR_QUOTA = "booking"  # clave de cuota/host en config, un solo pool para todo Booking.com15
CACHE_HOTELES = "booking_hoteles"
CACHE_VUELOS = "booking_vuelos"

ENDPOINT_HOTELES_DESTINO = "api/v1/hotels/searchDestination"
ENDPOINT_HOTELES_BUSCAR = "api/v1/hotels/searchHotels"
ENDPOINT_VUELOS_DESTINO = "api/v1/flights/searchDestination"
ENDPOINT_VUELOS_BUSCAR = "api/v1/flights/searchFlights"

# Orden de preferencia al elegir entre varios candidatos de searchDestination.
# Confirmado con llamadas reales: el campo viene en minuscula para hoteles
# ("city", "district", "region", "airport") y en mayuscula para vuelos
# ("CITY", "AIRPORT") -- son dos catalogos de valores distintos.
ORDEN_TIPO_HOTEL = ["city", "district", "region", "airport"]
ORDEN_TIPO_VUELO = ["CITY", "AIRPORT"]


def _verificar_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """El envelope de Booking miente sobre el exito: un error de parametros
    puede volver con HTTP 200 y `status: false`. Nunca confiar solo en el
    codigo HTTP (ver migracion-amadeus-a-rapidapi.md, seccion 5)."""
    if body.get("status") is not True:
        raise client.ErrorRapidAPI(f"Booking.com15 respondio status=false: {body.get('message')}")
    return body


def _elegir_candidato(candidatos: list[dict[str, Any]], campo_tipo: str, orden: list[str]) -> dict[str, Any]:
    if not candidatos:
        raise client.ErrorRapidAPI("searchDestination sin resultados")
    for tipo in orden:
        for candidato in candidatos:
            if candidato.get(campo_tipo) == tipo:
                return candidato
    return candidatos[0]


def resolver_destino_hotel(conexion: psycopg.Connection, texto: str) -> DestinoResuelto:
    """`dest_id` + `search_type` para `searchHotels`. Cacheado: esta
    resolucion no cambia nunca para un mismo texto de busqueda."""
    cacheado = buscar_destino_cacheado(conexion, CACHE_HOTELES, texto)
    if cacheado is not None:
        return cacheado

    configuracion = cargar_configuracion()
    body = _verificar_envelope(
        client.llamar(
            conexion, PROVEEDOR_QUOTA, configuracion.rapidapi_host_booking, ENDPOINT_HOTELES_DESTINO, {"query": texto}
        )
    )
    candidato = _elegir_candidato(body.get("data") or [], "search_type", ORDEN_TIPO_HOTEL)

    resuelto = DestinoResuelto(
        proveedor=CACHE_HOTELES,
        texto_consultado=texto,
        id_externo=str(candidato.get("dest_id")),
        tipo=candidato.get("search_type"),
        nombre=candidato.get("name") or candidato.get("city_name") or texto,
        pais=candidato.get("country"),
        lat=candidato.get("latitude"),
        lon=candidato.get("longitude"),
    )
    guardar_destino_cacheado(conexion, resuelto)
    return resuelto


def resolver_destino_vuelo(conexion: psycopg.Connection, texto: str) -> DestinoResuelto:
    """`id` (por ejemplo `"BUE.CITY"`) + `type` para `searchFlights`.
    Mismo patron de cache que `resolver_destino_hotel`, namespace distinto."""
    cacheado = buscar_destino_cacheado(conexion, CACHE_VUELOS, texto)
    if cacheado is not None:
        return cacheado

    configuracion = cargar_configuracion()
    body = _verificar_envelope(
        client.llamar(
            conexion, PROVEEDOR_QUOTA, configuracion.rapidapi_host_booking, ENDPOINT_VUELOS_DESTINO, {"query": texto}
        )
    )
    candidato = _elegir_candidato(body.get("data") or [], "type", ORDEN_TIPO_VUELO)

    resuelto = DestinoResuelto(
        proveedor=CACHE_VUELOS,
        texto_consultado=texto,
        id_externo=str(candidato.get("id")),
        tipo=candidato.get("type"),
        nombre=candidato.get("name") or candidato.get("cityName") or texto,
        pais=candidato.get("countryName"),
        lat=None,
        lon=None,
    )
    guardar_destino_cacheado(conexion, resuelto)
    return resuelto


def _precio_hotel(propiedad: dict[str, Any]) -> tuple[float | None, str | None]:
    precio = ((propiedad.get("priceBreakdown") or {}).get("grossPrice")) or {}
    return precio.get("value"), precio.get("currency")


def _a_alojamiento(hotel: dict[str, Any]) -> Alojamiento:
    """Unico lugar del proyecto que conoce la forma cruda de un hotel de
    Booking.com15. Todos los campos salvo nombre/proveedor son opcionales:
    el wrapper omite campos con frecuencia."""
    propiedad = hotel.get("property") or {}
    precio_total, moneda = _precio_hotel(propiedad)
    fotos = propiedad.get("photoUrls") or []
    return Alojamiento(
        nombre=propiedad.get("name") or "Alojamiento sin nombre",
        proveedor="booking",
        precio_total=precio_total,
        moneda=moneda,
        puntaje=propiedad.get("reviewScore"),
        cantidad_resenias=propiedad.get("reviewCount"),
        direccion=None,  # searchHotels no trae direccion, hace falta getHotelDetails
        url_imagen=fotos[0] if fotos else None,
    )


def _precio_vuelo(price_breakdown: dict[str, Any] | None) -> tuple[float | None, str | None]:
    total = (price_breakdown or {}).get("total") or {}
    if not total:
        return None, None
    monto = total.get("units", 0) + total.get("nanos", 0) / 1_000_000_000
    return round(monto, 2), total.get("currencyCode")


def _a_opcion_vuelo(oferta: dict[str, Any]) -> OpcionVuelo:
    """Unico lugar del proyecto que conoce la forma cruda de un flightOffer
    de Booking.com15. `segments[0]` es el tramo de ida; si hay un segundo
    segmento es la vuelta (ida y vuelta)."""
    segmentos = oferta.get("segments") or []
    primer_segmento = segmentos[0] if segmentos else {}
    legs = primer_segmento.get("legs") or []

    aerolineas: list[str] = []
    for leg in legs:
        for carrier in leg.get("carriersData") or []:
            nombre = carrier.get("name")
            if nombre and nombre not in aerolineas:
                aerolineas.append(nombre)

    precio_total, moneda = _precio_vuelo(oferta.get("priceBreakdown"))
    duracion = primer_segmento.get("totalTime")

    return OpcionVuelo(
        proveedor="booking",
        origen=(primer_segmento.get("departureAirport") or {}).get("code"),
        destino=(primer_segmento.get("arrivalAirport") or {}).get("code"),
        fecha_salida=primer_segmento.get("departureTime"),
        fecha_regreso=segmentos[1].get("departureTime") if len(segmentos) > 1 else None,
        precio_total=precio_total,
        moneda=moneda,
        aerolineas=aerolineas,
        escalas=max(len(legs) - 1, 0),
        duracion_minutos=(duracion // 60) if duracion else None,
    )


def _marcar_como_fixture(items: list[Alojamiento] | list[OpcionVuelo]) -> list[Any]:
    for item in items:
        item.es_fixture = True
    return items


def buscar_alojamiento(
    conexion: psycopg.Connection,
    destino: str,
    fecha_inicio: date,
    fecha_fin: date,
    adultos: int = 2,
    habitaciones: int = 1,
    moneda: str = "USD",
    idioma: str = "es",
) -> list[Alojamiento]:
    """RF6. Resuelve el destino (cacheado) y busca hoteles reales. Si
    Booking.com15 falla (cuota agotada u otro error sin reintento posible),
    sirve el fixture de demo marcado explicitamente como dato de ejemplo,
    para que el LLM nunca le afirme al usuario que son precios reales."""
    configuracion = cargar_configuracion()
    try:
        destino_resuelto = resolver_destino_hotel(conexion, destino)
        body = _verificar_envelope(
            client.llamar(
                conexion,
                PROVEEDOR_QUOTA,
                configuracion.rapidapi_host_booking,
                ENDPOINT_HOTELES_BUSCAR,
                {
                    "dest_id": destino_resuelto.id_externo,
                    "search_type": destino_resuelto.tipo,
                    "arrival_date": fecha_inicio.isoformat(),
                    "departure_date": fecha_fin.isoformat(),
                    "adults": adultos,
                    "room_qty": habitaciones,
                    "currency_code": moneda,
                    "languagecode": idioma,
                },
            )
        )
        hoteles = (body.get("data") or {}).get("hotels") or []
        return [_a_alojamiento(hotel) for hotel in hoteles]
    except client.ErrorRapidAPI as error:
        logger.warning("buscar_alojamiento(%s) fallo, sirviendo fixture: %s", destino, error)
        body = client.leer_fixture(PROVEEDOR_QUOTA, ENDPOINT_HOTELES_BUSCAR)
        hoteles = (body.get("data") or {}).get("hotels") or []
        return _marcar_como_fixture([_a_alojamiento(hotel) for hotel in hoteles])


def buscar_vuelos(
    conexion: psycopg.Connection,
    origen: str,
    destino: str,
    fecha_salida: date,
    fecha_regreso: date | None = None,
    adultos: int = 1,
    moneda: str = "USD",
) -> list[OpcionVuelo]:
    """RF7. Resuelve origen y destino (cacheados) y busca vuelos reales.
    Mismo criterio de fixture marcado que `buscar_alojamiento` si falla."""
    configuracion = cargar_configuracion()
    try:
        origen_resuelto = resolver_destino_vuelo(conexion, origen)
        destino_resuelto = resolver_destino_vuelo(conexion, destino)
        parametros = {
            "fromId": origen_resuelto.id_externo,
            "toId": destino_resuelto.id_externo,
            "departDate": fecha_salida.isoformat(),
            "adults": adultos,
            "currency_code": moneda,
            "cabinClass": "ECONOMY",
        }
        if fecha_regreso is not None:
            parametros["returnDate"] = fecha_regreso.isoformat()

        body = _verificar_envelope(
            client.llamar(
                conexion, PROVEEDOR_QUOTA, configuracion.rapidapi_host_booking, ENDPOINT_VUELOS_BUSCAR, parametros
            )
        )
        ofertas = (body.get("data") or {}).get("flightOffers") or []
        return [_a_opcion_vuelo(oferta) for oferta in ofertas]
    except client.ErrorRapidAPI as error:
        logger.warning("buscar_vuelos(%s -> %s) fallo, sirviendo fixture: %s", origen, destino, error)
        body = client.leer_fixture(PROVEEDOR_QUOTA, ENDPOINT_VUELOS_BUSCAR)
        ofertas = (body.get("data") or {}).get("flightOffers") or []
        return _marcar_como_fixture([_a_opcion_vuelo(oferta) for oferta in ofertas])
