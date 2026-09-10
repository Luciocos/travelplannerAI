"""Retriever del corpus de FAQ del viajero (RF9, extension). Texto curado
a mano por destino sobre seguridad, estafas comunes y costumbres."""

from __future__ import annotations

import psycopg

from asistente_viajes.recuperacion._consulta import ResultadoRecuperado, buscar

CORPUS = "faq"


def buscar_faq(
    conexion: psycopg.Connection, destino: str, consulta: str, k: int = 3
) -> list[ResultadoRecuperado]:
    """Filtra por destino, busca semanticamente por la pregunta del usuario."""
    return buscar(conexion, corpus=CORPUS, destino=destino, consulta=consulta, k=k)
