"""Tabla de costos base para estimar el presupuesto de un itinerario.

El costo estimado de armar_plan (RF5) sale de aca y del rango_precio del
corpus, nunca de un numero inventado por el LLM (ver arquitectura.md).
Son estimaciones ilustrativas en una unidad monetaria generica, no estan
ligadas todavia a la moneda real del destino (eso depende de RF8 y de
resolver los destinos piloto a ciudades concretas, ver DECISIONES.md D-04).
Ajustar estos valores es una decision de producto, no un detalle tecnico:
documentar el cambio en docs/DECISIONES.md si se tocan.
"""

from __future__ import annotations

# Costo base estimado por categoria de atractivo, cuando el documento no
# trae rango_precio (lo mas comun en atractivos, mas frecuente en comercios).
COSTO_BASE_POR_CATEGORIA: dict[str, float] = {
    "historic": 5.0,
    "museums": 10.0,
    "natural": 0.0,
    "cultural": 8.0,
    "architecture": 0.0,
    "foods": 15.0,
    "shops": 20.0,
    "marketplaces": 10.0,
}

COSTO_POR_DEFECTO = 10.0

# Mapeo de rango_precio (convencion "$".."$$$$") a costo estimado. Se usa
# cuando el documento (tipicamente curado a mano) trae rango_precio.
COSTO_POR_RANGO_PRECIO: dict[str, float] = {
    "$": 10.0,
    "$$": 25.0,
    "$$$": 50.0,
    "$$$$": 100.0,
}


def estimar_costo(categoria: str | None, rango_precio: str | None) -> float:
    """rango_precio manda si esta presente (viene de datos curados a mano,
    mas confiable). Si no, se usa el costo base de la categoria. Si no hay
    ninguno de los dos, el costo por defecto."""
    if rango_precio and rango_precio in COSTO_POR_RANGO_PRECIO:
        return COSTO_POR_RANGO_PRECIO[rango_precio]
    if categoria and categoria in COSTO_BASE_POR_CATEGORIA:
        return COSTO_BASE_POR_CATEGORIA[categoria]
    return COSTO_POR_DEFECTO
