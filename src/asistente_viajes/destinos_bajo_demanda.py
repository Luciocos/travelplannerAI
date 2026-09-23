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
    buscar_en_varios_puntos,
    detalles_de_xids,
    geolocalizar,
)

logger = logging.getLogger(__name__)

DIRECTORIO_RAW = Path(__file__).resolve().parent.parent.parent / "data" / "raw"

# Radio amplio a proposito: el geocoder devuelve UN punto (en Tokio cae en
# Shinjuku) y los atractivos de una ciudad grande estan repartidos. Con un
# radio chico el corpus se llena de lo que rodea ese punto exacto.
RADIO_METROS = 25000
# La lista del paso 1 es una sola llamada, asi que se pide grande y se
# filtra por relevancia; los detalles, que son una llamada por POI, se le
# traen solo a los mejores (ver ingerir_destino, limite_detalles).
LIMITE_LISTA = 300
LIMITE_POIS = 45

# Filtro de significancia de OpenTripMap. El campo `rate` va de 0 a 7 (los
# valores altos son patrimonio declarado), aunque el parametro de la API
# acepte '1'..'3'/'h' como minimo. Con rate=3 quedan afuera los comercios y
# edificios anonimos que igual tienen articulo de Wikipedia, que es lo que
# arruino los corpus de Barcelona y Tokio.
RATE_MINIMO_ATRACTIVOS = "3"

KINDS_ATRACTIVOS = [
    "historic",
    "museums",
    "natural",
    "cultural",
    "architecture",
    "religion",
    "urban_environment",
    "amusements",
]

# Cuantos POIs se puntuan (ver _puntaje_relevancia) para quedarse con los
# LIMITE_POIS mejores. Traer el detalle de mas candidatos cuesta tiempo,
# pero es la unica forma de elegir por relevancia real: el paso 1 no dice
# nada util para ordenar (en Barcelona hay cientos de POIs empatados en
# rate=7, el maximo, asi que el rate no discrimina).
CANDIDATOS_A_PUNTUAR = 110
# No se usan en el camino interactivo (ver _ingerir); quedan para la
# ingesta offline de scripts/ingestar_destino.py.
KINDS_COMERCIOS = ["foods", "shops", "marketplaces"]

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


def _puntaje_relevancia(detalle: dict) -> float:
    """Cuán "visitable" parece un POI, con lo que ya vino en su detalle (no
    cuesta ninguna llamada extra).

    Se intentaron primero señales externas y ninguna sirvió: el `rate` de
    OpenTripMap satura (en Barcelona cientos de POIs empatan en 7, el
    máximo), los pageviews de la API de Wikipedia vuelven vacíos para
    artículos que claramente tienen visitas, y la consulta SPARQL a
    Wikidata por cantidad de idiomas da timeout sobre una búsqueda
    geográfica. Lo que sí discrimina, y está gratis en la respuesta:

    - Tener imagen. Un lugar que la gente visita y fotografía tiene foto en
      Wikimedia; una casa anónima del Eixample, no.
    - El largo del extracto de Wikipedia. Un artículo largo es proxy de
      cuánto se escribió sobre el lugar.
    - Estar en varias categorías (un sitio importante suele ser a la vez
      histórico, arquitectónico y cultural).
    """
    extracto = (detalle.get("wikipedia_extracts") or {}).get("text") or ""
    tiene_imagen = bool(detalle.get("preview") or detalle.get("image"))
    kinds = [k for k in (detalle.get("kinds") or "").split(",") if k]

    # `rate` puede venir como numero o como "3h": el sufijo 'h' marca
    # patrimonio declarado (UNESCO y similares), asi que ademas de no
    # romper el float(), suma como senial fuerte de relevancia.
    rate_crudo = str(detalle.get("rate") or "0")
    digitos = "".join(c for c in rate_crudo if c.isdigit())
    puntaje = float(digitos or 0)
    if "h" in rate_crudo.lower():
        puntaje += 5.0

    puntaje += 4.0 if tiene_imagen else 0.0
    puntaje += min(len(extracto) / 400.0, 6.0)
    puntaje += min(len(kinds) * 0.3, 2.0)
    return puntaje


def _puntos_de_muestreo(lat: float, lon: float) -> list[tuple[float, float]]:
    """Solo el centro del destino, y eso es una conclusion, no una
    simplificacion pendiente.

    Se probo muestrear tambien desde un anillo de 4 puntos a 4 km,
    intercalando los resultados, para que el cupo de la busqueda por radio
    no se agotara en el centro. Medido contra la API real, empeoro las dos
    ciudades de prueba: al repartir el cupo en partes iguales, 4 de cada 5
    candidatos salian de zonas residenciales. Barcelona paso a devolver
    casonas de barrio ("Can Bacardi", "Can Querol") y Tokio perdio el
    Castillo Edo y el santuario Meiji Jingu a cambio de plazas de Suginami.
    El centro concentra los atractivos, asi que darle el cupo entero es lo
    que mejor corpus produce. Se deja la funcion (y el parametro `puntos`
    de buscar_en_varios_puntos) porque la forma correcta de retomarlo seria
    ponderar, no repartir en partes iguales.
    """
    return [(lat, lon)]


def _ingerir(nombre: str, lat: float, lon: float, api_key: str) -> int:
    """Trae los atractivos del destino y los carga a pgvector. Devuelve
    cuantos documentos se escribieron."""
    # Solo atractivos: esto corre dentro de un turno de chat y cada kind
    # extra duplica las llamadas a la API (y la espera del cliente). El
    # corpus de comercios es una extension con datos flacos de por si
    # (D-07), asi que no justifica el costo en el camino interactivo; se
    # sigue pudiendo cargar aparte con scripts/ingestar_destino.py.
    documentos: list[DocumentoCorpus] = []
    candidatos = buscar_en_varios_puntos(
        api_key,
        puntos=_puntos_de_muestreo(lat, lon),
        radio_metros=RADIO_METROS,
        kinds=KINDS_ATRACTIVOS,
        limite_por_punto=LIMITE_LISTA,
        rate=RATE_MINIMO_ATRACTIVOS,
    )
    if not candidatos:
        logger.warning("no se encontraron POIs para %s", nombre)
        return 0

    # `candidatos` ya viene intercalado por punto de muestreo, y ese orden
    # se respeta: re-ordenarlo por `rate` aca fue un error real, porque el
    # rate satura en 7 y la lista volvia a quedar dominada por el centro,
    # tirando a la basura la diversidad geografica recien ganada.
    xids = [poi["xid"] for poi in candidatos[:CANDIDATOS_A_PUNTUAR] if poi.get("xid")]
    detalles = detalles_de_xids(api_key, xids)

    mejores = sorted(detalles, key=_puntaje_relevancia, reverse=True)[:LIMITE_POIS]
    for detalle in mejores:
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
