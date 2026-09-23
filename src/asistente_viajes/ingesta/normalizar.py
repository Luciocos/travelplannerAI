"""Normaliza un detalle crudo de OpenTripMap (o un registro curado a mano)
a un DocumentoCorpus, la forma comun que consume la carga a pgvector.

Regla dura: si no hay texto descriptivo real (extracto de Wikipedia u otro
campo con contenido), el POI se descarta. No se inventa texto con el LLM
para poder embeberlo, eso violaria la restriccion de datos no inventados.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from asistente_viajes.texto import normalizar

LONGITUD_MINIMA_TEXTO = 200

# religion y urban_environment faltaban, y no era un detalle: dejaban fuera
# del corpus a catedrales, templos, parques y plazas, o sea buena parte de
# lo mas visitado de cualquier ciudad (la Sagrada Familia y el Senso-ji son
# 'religion'; el Retiro o Central Park, 'urban_environment'). Un POI cuyos
# kinds no matchean ningun corpus se descarta en silencio, asi que el
# efecto era invisible salvo mirando el corpus resultante.
CATEGORIAS_ATRACTIVOS = {
    "historic",
    "museums",
    "natural",
    "cultural",
    "architecture",
    "religion",
    "urban_environment",
    "amusements",
}
CATEGORIAS_COMERCIOS = {"foods", "shops", "marketplaces"}

# Kinds que OpenTripMap mete bajo "architecture"/"interesting_places" pero que
# no son atractivos turisticos reales: torres de departamentos, oficinas y
# hoteles (ver P-08 en DIFICULTADES.md, hallado con el corpus real de Miami:
# 49 de 75 "atractivos" eran edificios residenciales sin nada que visitar).
# Se descarta por el kind PRIMARIO (el primero de la lista, el que pasa a
# `categoria`), no por interseccion: un lugar realmente historico puede tener
# "architecture" como kind secundario sin ser, en sí, una torre generica.
CATEGORIAS_EXCLUIDAS_COMO_PRIMARIO = {"skyscrapers", "other_buildings", "resorts", "accomodations"}

TipoCorpus = Literal["atractivos", "comercios", "faq"]


class DocumentoCorpus(BaseModel):
    corpus: TipoCorpus
    destino: str
    nombre: str | None = None
    categoria: str | None = None
    texto: str
    direccion: str | None = None
    rango_precio: str | None = None
    lat: float | None = None
    lon: float | None = None
    fuente: str  # 'opentripmap' | 'curado'
    xid: str | None = None


def _corpus_por_kinds(kinds: str) -> TipoCorpus | None:
    categorias = set(kinds.split(","))
    if categorias & CATEGORIAS_ATRACTIVOS:
        return "atractivos"
    if categorias & CATEGORIAS_COMERCIOS:
        return "comercios"
    return None


def _extraer_texto(detalle: dict) -> str:
    wikipedia_extractos = detalle.get("wikipedia_extracts") or {}
    texto = wikipedia_extractos.get("text") or ""
    if not texto:
        texto = detalle.get("info", {}).get("descr") or ""
    return texto.strip()


def normalizar_poi_opentripmap(detalle: dict, destino: str) -> DocumentoCorpus | None:
    """POI crudo de OpenTripMap -> DocumentoCorpus, o None si no alcanza
    la longitud minima de texto, no matchea ningun corpus conocido, o su
    kind primario esta en CATEGORIAS_EXCLUIDAS_COMO_PRIMARIO (torres de
    departamentos, hoteles, ver P-08)."""
    kinds = detalle.get("kinds", "")
    if kinds.split(",")[0] in CATEGORIAS_EXCLUIDAS_COMO_PRIMARIO:
        return None

    corpus = _corpus_por_kinds(kinds)
    if corpus is None:
        return None

    texto = _extraer_texto(detalle)
    if len(texto) < LONGITUD_MINIMA_TEXTO:
        return None

    punto = detalle.get("point", {})
    direccion_dict = detalle.get("address", {})
    direccion = (
        ", ".join(
            parte for parte in (direccion_dict.get("road"), direccion_dict.get("city")) if parte
        )
        or None
    )

    return DocumentoCorpus(
        corpus=corpus,
        destino=destino,
        nombre=detalle.get("name") or None,
        categoria=kinds.split(",")[0] if kinds else None,
        texto=texto,
        direccion=direccion,
        rango_precio=None,
        lat=punto.get("lat"),
        lon=punto.get("lon"),
        fuente="opentripmap",
        xid=detalle.get("xid"),
    )


def deduplicar_documentos(documentos: list[DocumentoCorpus]) -> list[DocumentoCorpus]:
    """Descarta duplicados por (corpus, destino, nombre normalizado),
    quedandose con el texto mas largo de cada grupo (ver P-08: Barcelona
    tenia "Font ornamental del passeig de Gracia" 3 veces, con distinto xid
    de OpenTripMap para el mismo lugar). Documentos sin nombre nunca se
    consideran duplicados entre si."""
    mejores: dict[tuple[str, str, str], DocumentoCorpus] = {}
    sin_nombre: list[DocumentoCorpus] = []

    for documento in documentos:
        if not documento.nombre:
            sin_nombre.append(documento)
            continue
        clave = (documento.corpus, normalizar(documento.destino), normalizar(documento.nombre))
        actual = mejores.get(clave)
        if actual is None or len(documento.texto) > len(actual.texto):
            mejores[clave] = documento

    return list(mejores.values()) + sin_nombre


def _slug_curado(corpus: str, destino: str, nombre: str) -> str:
    """xid deterministico para un registro curado, a partir de
    corpus+destino+nombre. Hace que cargar_documentos (upsert por xid) sea
    idempotente: re-correr la carga actualiza el mismo registro en vez de
    insertar un duplicado (ver P-08 en DIFICULTADES.md)."""
    partes = f"{corpus}-{destino}-{nombre}"
    return "curado-" + re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", normalizar(partes))).strip("-")


def normalizar_curado(registro: dict) -> DocumentoCorpus:
    """Registro completado a mano en data/curated/ -> DocumentoCorpus.
    No pasa por el filtro de longitud minima: se asume que quien lo carga
    a mano ya escribio un texto util. fuente queda fija en 'curado'. Si el
    registro no trae xid propio, se genera uno deterministico (ver
    _slug_curado) para que la carga sea idempotente."""
    xid = registro.get("xid") or _slug_curado(
        registro["corpus"], registro["destino"], registro.get("nombre") or registro["texto"][:50]
    )
    return DocumentoCorpus(
        corpus=registro["corpus"],
        destino=registro["destino"],
        nombre=registro.get("nombre"),
        categoria=registro.get("categoria"),
        texto=registro["texto"],
        direccion=registro.get("direccion"),
        rango_precio=registro.get("rango_precio"),
        lat=registro.get("lat"),
        lon=registro.get("lon"),
        fuente="curado",
        xid=xid,
    )
