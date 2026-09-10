"""Retriever del corpus de atractivos turisticos. Alimenta
recomendar_actividades y armar_plan (RF3)."""

from __future__ import annotations

import psycopg

from asistente_viajes.recuperacion._consulta import ResultadoRecuperado, buscar

CORPUS = "atractivos"


def buscar_atractivos(
    conexion: psycopg.Connection, destino: str, intereses: list[str], k: int = 5
) -> list[ResultadoRecuperado]:
    """Filtra por destino, busca semanticamente por los intereses declarados."""
    consulta = ", ".join(intereses) if intereses else destino
    return buscar(conexion, corpus=CORPUS, destino=destino, consulta=consulta, k=k)
