"""Ingesta de un destino la primera vez que alguien lo nombra (D-23).

Hasta la Fase 7D el asistente solo sabia responder por 3 destinos
precargados a mano: cualquier otro caia en "destino_fuera_de_alcance" y el
cliente recibia un "por ahora no tengo datos de X". Eso convertia a un
asistente de viajes en un folleto de tres ciudades.

Acá el flujo es otro: si el destino ya tiene corpus en pgvector, se usa
(camino rapido, sin red). Si no, se resuelve el nombre contra el geoname de
OpenTripMap, se ingieren sus POIs, se embeben y se guardan. A partir de ese
momento el destino queda cargado para siempre y las consultas siguientes no
vuelven a pegarle a la API. El corpus crece solo, con datos reales.

Lo que NO cambia: nada se inventa. Si OpenTripMap no reconoce el lugar,
devolvemos None y el asistente lo dice; si lo reconoce pero no hay POIs con
texto descriptivo real, el destino queda cargado con lo que haya y la
cantidad se informa, para que la redaccion pueda ser honesta sobre cuanto
material tiene.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg
from pydantic import BaseModel

from asistente_viajes.destinos import buscar_destino_piloto
from asistente_viajes.ingesta.cargar_vectores import cargar_documentos
from asistente_viajes.ingesta.normalizar import (
    DocumentoCorpus,
    deduplicar_documentos,
    normalizar_poi_opentripmap,
)
from asistente_viajes.ingesta.opentripmap import (
    ErrorOpenTripMap,
    geolocalizar,
    ingerir_destino,
)

logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path(__file__).resolve().parent.parent.parent / "data" / "raw"

RADIO_METROS = 12000
LIMITE_POIS = 60

# Filtro de significancia de OpenTripMap ('1' a '3', 'h'). Sin esto, la
# busqueda por radio devuelve los primeros N POIs por cercania y en un
# centro historico eso llena el cupo de casas y edificios anonimos que
# igual tienen articulo de Wikipedia (fue exactamente lo que le paso al
# corpus de Barcelona: 39 "atractivos" sin la Sagrada Familia). Con rate=2
# entran primero los lugares con relevancia turistica declarada.
RATE_MINIMO_ATRACTIVOS = "2"

KINDS_ATRACTIVOS = ["historic", "museums", "natural", "cultural", "architecture"]
KINDS_COMERCIOS = ["foods", "shops", "marketplaces"]  # no se usan en el camino interactivo, ver _ingerir

SQL_CONTAR_DOCUMENTOS = """
SELECT corpus, count(*)
FROM documento_rag
WHERE lower(unaccent(destino)) = lower(unaccent(%(destino)s))
GROUP BY corpus;
"""

SQL_NOMBRE_CANONICO = """
SELECT destino
FROM documento_rag
WHERE lower(unaccent(destino)) = lower(unaccent(%(destino)s))
LIMIT 1;
"""


class DestinoResuelto(BaseModel):
    """Un destino que el asistente ya puede responder."""

    nombre: str
    lat: float
    lon: float
    pais: str | None = None  # codigo ISO-2 cuando viene de geoname
    atractivos: int = 0
    recien_ingerido: bool = False


def _conteo_por_corpus(conexion: psycopg.Connection, destino: str) -> dict[str, int]:
    with conexion.cursor() as cursor:
        cursor.execute(SQL_CONTAR_DOCUMENTOS, {"destino": destino})
        return {corpus: cantidad for corpus, cantidad in cursor.fetchall()}


def _nombre_canonico(conexion: psycopg.Connection, destino: str) -> str | None:
    """El nombre tal como quedo guardado, para no terminar con 'cancun',
    'Cancun' y 'CANCUN' como tres destinos distintos en la base."""
    with conexion.cursor() as cursor:
        cursor.execute(SQL_NOMBRE_CANONICO, {"destino": destino})
        fila = cursor.fetchone()
        return fila[0] if fila else None


def _coordenadas_conocidas(destino: str) -> tuple[str, float, float, str | None] | None:
    """Un destino piloto ya tiene coordenadas curadas en destinos.json; se
    prefieren a las de geoname porque estan elegidas a mano."""
    encontrado = buscar_destino_piloto(destino)
    if encontrado is None:
        return None
    nombre, datos = encontrado
    return nombre, datos["lat"], datos["lon"], datos.get("pais")


def _ingerir(nombre: str, lat: float, lon: float, api_key: str) -> int:
    """Trae los atractivos del destino y los carga a pgvector. Devuelve
    cuantos documentos se escribieron."""
    # Solo atractivos: esto corre dentro de un turno de chat y cada kind
    # extra duplica las llamadas a la API (y la espera del cliente). El
    # corpus de comercios es una extension con datos flacos de por si
    # (D-07), asi que no justifica el costo en el camino interactivo; se
    # sigue pudiendo cargar aparte con scripts/ingestar_destino.py.
    documentos: list[DocumentoCorpus] = []
    try:
        detalles = ingerir_destino(
            destino=nombre,
            lat=lat,
            lon=lon,
            radio_metros=RADIO_METROS,
            api_key=api_key,
            directorio_raw=DIRECTORIO_RAW,
            kinds=KINDS_ATRACTIVOS,
            limite=LIMITE_POIS,
            rate=RATE_MINIMO_ATRACTIVOS,
        )
    except ErrorOpenTripMap:
        logger.warning("fallo la ingesta de %s", nombre, exc_info=True)
        return 0

    for detalle in detalles:
        documento = normalizar_poi_opentripmap(detalle, destino=nombre)
        if documento is not None:
            documentos.append(documento)

    if not documentos:
        return 0
    return cargar_documentos(deduplicar_documentos(documentos))


def asegurar_destino(
    conexion: psycopg.Connection, destino: str, minimo_atractivos: int = 1
) -> DestinoResuelto | None:
    """Deja el destino listo para consultar y devuelve sus datos, o None si
    el lugar no existe (no lo reconoce el geocoder).

    Tres caminos, en orden de costo:
    1. Ya tiene corpus cargado -> se devuelve tal cual, sin tocar la red.
    2. Es un destino piloto con coordenadas curadas -> se ingiere con esas.
    3. Cualquier otro -> se resuelve por geoname y se ingiere.
    """
    conteo = _conteo_por_corpus(conexion, destino)
    atractivos = conteo.get("atractivos", 0)

    conocido = _coordenadas_conocidas(destino)
    if atractivos >= minimo_atractivos:
        nombre = _nombre_canonico(conexion, destino) or destino
        lat, lon, pais = (conocido[1], conocido[2], conocido[3]) if conocido else (0.0, 0.0, None)
        if not conocido:
            # Un destino ingerido bajo demanda no esta en destinos.json, asi
            # que sus coordenadas hay que volver a resolverlas para RF8
            # (clima). Es una llamada barata y cacheada por el geocoder.
            ubicacion = _geolocalizar_seguro(destino)
            if isinstance(ubicacion, dict):
                lat, lon, pais = ubicacion["lat"], ubicacion["lon"], ubicacion.get("country")
        return DestinoResuelto(
            nombre=nombre, lat=lat, lon=lon, pais=pais, atractivos=atractivos
        )

    if conocido:
        nombre, lat, lon, pais = conocido
    else:
        ubicacion = _geolocalizar_seguro(destino)
        if ubicacion is None:
            # El geocoder contesto y dijo que ese lugar no existe. Es el
            # unico caso en el que el asistente puede afirmarlo.
            return None
        if ubicacion is NO_VERIFICABLE:
            # No se pudo comprobar. Se sigue con el destino tal como lo
            # dijo el cliente: si ya tenia corpus las consultas andan igual,
            # y si no, el turno lo va a reflejar con cero atractivos.
            return DestinoResuelto(nombre=destino, lat=0.0, lon=0.0, atractivos=atractivos)
        nombre = ubicacion.get("name") or destino
        lat, lon, pais = ubicacion["lat"], ubicacion["lon"], ubicacion.get("country")

    api_key = os.environ.get("OPENTRIPMAP_API_KEY")
    if not api_key:
        return DestinoResuelto(
            nombre=nombre, lat=lat, lon=lon, pais=pais, atractivos=atractivos
        )

    logger.info("ingiriendo %s bajo demanda (lat=%s, lon=%s)", nombre, lat, lon)
    _ingerir(nombre, lat, lon, api_key)
    atractivos = _conteo_por_corpus(conexion, nombre).get("atractivos", 0)

    return DestinoResuelto(
        nombre=nombre,
        lat=lat,
        lon=lon,
        pais=pais,
        atractivos=atractivos,
        recien_ingerido=True,
    )


# Tercer estado, ademas de "lo encontre" (dict) y "no existe" (None): "no
# pude averiguarlo". Confundirlo con "no existe" seria un bug caro: sin
# API key o sin red, TODOS los destinos pasarian a ser inexistentes y el
# asistente le diria al cliente que su ciudad no existe.
NO_VERIFICABLE = object()


def _geolocalizar_seguro(destino: str) -> dict | None | object:
    """geolocalizar() sin propagar errores de red. Devuelve el lugar, None
    si el geocoder dice que no existe, o NO_VERIFICABLE si no se pudo
    consultar (falta la clave, la API no contesta)."""
    api_key = os.environ.get("OPENTRIPMAP_API_KEY")
    if not api_key:
        logger.warning("sin OPENTRIPMAP_API_KEY, no se puede verificar '%s'", destino)
        return NO_VERIFICABLE
    try:
        return geolocalizar(api_key, destino)
    except ErrorOpenTripMap:
        logger.warning("fallo geoname para %s", destino, exc_info=True)
        return NO_VERIFICABLE
