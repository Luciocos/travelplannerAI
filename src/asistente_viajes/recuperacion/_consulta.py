"""Consulta canonica de los tres RAGs: filtro por metadata (corpus, destino)
y busqueda semantica, las dos cosas en una sola query SQL (ver
arquitectura.md, es el argumento concreto a favor de pgvector).
"""

from __future__ import annotations

import psycopg
from pydantic import BaseModel

from asistente_viajes.embeddings import embeber_texto

SQL_CONSULTA_CANONICA = """
SELECT nombre, categoria, texto, direccion, rango_precio
FROM documento_rag
WHERE corpus = %(corpus)s AND destino = %(destino)s
ORDER BY embedding <=> %(consulta)s::vector
LIMIT %(k)s;
"""


class ResultadoRecuperado(BaseModel):
    nombre: str | None = None
    categoria: str | None = None
    texto: str
    direccion: str | None = None
    rango_precio: str | None = None


def buscar(
    conexion: psycopg.Connection,
    corpus: str,
    destino: str,
    consulta: str,
    k: int = 5,
) -> list[ResultadoRecuperado]:
    """Filtra por corpus y destino, ordena por similitud semantica con la
    consulta. Primero filtra por metadata, recien ahi busca por embedding,
    todo en una sola consulta SQL."""
    vector_consulta = embeber_texto(consulta)

    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_CONSULTA_CANONICA,
            {"corpus": corpus, "destino": destino, "consulta": vector_consulta, "k": k},
        )
        filas = cursor.fetchall()

    columnas = ["nombre", "categoria", "texto", "direccion", "rango_precio"]
    return [ResultadoRecuperado(**dict(zip(columnas, fila, strict=True))) for fila in filas]
