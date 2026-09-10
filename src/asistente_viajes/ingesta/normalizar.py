"""Normaliza un detalle crudo de OpenTripMap (o un registro curado a mano)
a un DocumentoCorpus, la forma comun que consume la carga a pgvector.

Regla dura: si no hay texto descriptivo real (extracto de Wikipedia u otro
campo con contenido), el POI se descarta. No se inventa texto con el LLM
para poder embeberlo, eso violaria la restriccion de datos no inventados.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

LONGITUD_MINIMA_TEXTO = 200

CATEGORIAS_ATRACTIVOS = {"historic", "museums", "natural", "cultural", "architecture"}
CATEGORIAS_COMERCIOS = {"foods", "shops", "marketplaces"}

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
    la longitud minima de texto o no matchea ningun corpus conocido."""
    kinds = detalle.get("kinds", "")
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


def normalizar_curado(registro: dict) -> DocumentoCorpus:
    """Registro completado a mano en data/curated/ -> DocumentoCorpus.
    No pasa por el filtro de longitud minima: se asume que quien lo carga
    a mano ya escribio un texto util. fuente queda fija en 'curado'."""
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
        xid=registro.get("xid"),
    )
