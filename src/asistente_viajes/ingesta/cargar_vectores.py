"""Embebe DocumentoCorpus y hace upsert en la tabla documento_rag.

Implementado contra la tabla propia de sql/001_schema.sql (ver decision
abierta de Fase 2 en arquitectura.md: PGVector oficial vs tabla propia).
Se eligio arrancar por la tabla propia porque ya estaba escrita en Fase 0
y el upsert por xid es directo; si aparece friccion, migrar a
langchain_postgres.PGVector envolviendo esto en un BaseRetriever, y
documentarlo como decision con su motivo.
"""

from __future__ import annotations

import logging

from asistente_viajes.db import obtener_conexion
from asistente_viajes.embeddings import embeber_textos
from asistente_viajes.ingesta.normalizar import DocumentoCorpus

logger = logging.getLogger(__name__)

_SQL_UPSERT_CON_XID = """
INSERT INTO documento_rag
    (corpus, destino, nombre, categoria, texto, direccion, rango_precio, lat, lon, fuente, xid, embedding)
VALUES
    (%(corpus)s, %(destino)s, %(nombre)s, %(categoria)s, %(texto)s, %(direccion)s,
     %(rango_precio)s, %(lat)s, %(lon)s, %(fuente)s, %(xid)s, %(embedding)s)
ON CONFLICT (xid) DO UPDATE SET
    corpus = EXCLUDED.corpus,
    destino = EXCLUDED.destino,
    nombre = EXCLUDED.nombre,
    categoria = EXCLUDED.categoria,
    texto = EXCLUDED.texto,
    direccion = EXCLUDED.direccion,
    rango_precio = EXCLUDED.rango_precio,
    lat = EXCLUDED.lat,
    lon = EXCLUDED.lon,
    fuente = EXCLUDED.fuente,
    embedding = EXCLUDED.embedding;
"""

_SQL_INSERT_SIN_XID = """
INSERT INTO documento_rag
    (corpus, destino, nombre, categoria, texto, direccion, rango_precio, lat, lon, fuente, xid, embedding)
VALUES
    (%(corpus)s, %(destino)s, %(nombre)s, %(categoria)s, %(texto)s, %(direccion)s,
     %(rango_precio)s, %(lat)s, %(lon)s, %(fuente)s, %(xid)s, %(embedding)s);
"""


def cargar_documentos(documentos: list[DocumentoCorpus]) -> int:
    """Embebe en batch y hace upsert de cada documento. Los registros con
    xid (vienen de OpenTripMap) se actualizan si ya existian, para poder
    re-correr la ingesta sin duplicar. Los curados sin xid se insertan
    directo, se deduplican a mano si hace falta.

    Devuelve la cantidad de filas escritas.
    """
    if not documentos:
        return 0

    textos = [documento.texto for documento in documentos]
    embeddings = embeber_textos(textos)

    with obtener_conexion() as conexion, conexion.cursor() as cursor:
        for documento, embedding in zip(documentos, embeddings, strict=True):
            parametros = documento.model_dump()
            parametros["embedding"] = embedding
            sql = _SQL_UPSERT_CON_XID if documento.xid else _SQL_INSERT_SIN_XID
            cursor.execute(sql, parametros)

    logger.info("cargados %s documentos", len(documentos))
    return len(documentos)
