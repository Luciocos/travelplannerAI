"""Retriever del corpus de comercios y gastronomia. Alimenta
recomendar_locales (RF4)."""

from __future__ import annotations

import psycopg

from asistente_viajes.recuperacion._consulta import ResultadoRecuperado, buscar

CORPUS = "comercios"


def buscar_comercios(
    conexion: psycopg.Connection, destino: str, consulta: str, k: int = 5
) -> list[ResultadoRecuperado]:
    """Filtra por destino, busca semanticamente por la consulta puntual del usuario
    (por ejemplo "donde comer barato" o "artesanias tipicas")."""
    return buscar(conexion, corpus=CORPUS, destino=destino, consulta=consulta, k=k)
