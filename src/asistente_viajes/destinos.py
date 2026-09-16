"""Datos de referencia de los destinos piloto (pais, coordenadas,
caracteristicas): data/reference/destinos.json. Punto unico de lectura,
para que agente.py (coordenadas para info_destino) y completar_slots.py
(caracteristicas para interpretar descripciones regionales) no dupliquen
la ruta ni el parseo.
"""

from __future__ import annotations

import json
from pathlib import Path

from asistente_viajes.texto import normalizar

RUTA_DESTINOS = (
    Path(__file__).resolve().parent.parent.parent / "data" / "reference" / "destinos.json"
)


def cargar_destinos_piloto(ruta: Path = RUTA_DESTINOS) -> dict[str, dict]:
    """Nombre de destino (tal como lo usa PreferenciasViaje.destino) ->
    {pais, lat, lon, caracteristicas}. Descarta claves de metadata (ej.
    '_comentario')."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {nombre: valor for nombre, valor in datos.items() if not nombre.startswith("_")}


def buscar_destino_piloto(destino: str, ruta: Path = RUTA_DESTINOS) -> tuple[str, dict] | None:
    """Busca un destino piloto insensible a tildes/mayusculas. Devuelve el
    nombre canonico (como esta en destinos.json) y sus datos, o None si no
    es uno de los destinos piloto."""
    destinos = cargar_destinos_piloto(ruta)
    normalizados = {normalizar(nombre): (nombre, valor) for nombre, valor in destinos.items()}
    return normalizados.get(normalizar(destino))
