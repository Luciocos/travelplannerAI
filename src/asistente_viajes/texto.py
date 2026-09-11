"""Utilidad chica de texto, compartida entre modulos (cache de RapidAPI,
orquestador, slot filling). Sin dependencias nuevas.
"""

from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """lower, sin tildes, trim. Para comparar texto libre (nombres de
    destino, sobre todo) sin que la tilde o la mayuscula rompa el match."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()
