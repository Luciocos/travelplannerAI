"""Tabla de costos base para estimar el presupuesto de un itinerario.

El costo estimado de armar_plan (RF5) sale de aca y del rango_precio del
corpus, nunca de un numero inventado por el LLM (ver arquitectura.md). Son
estimaciones ilustrativas en USD (misma unidad que ya usan buscar_alojamiento
y buscar_vuelos, RF6/RF7), pensadas para que el itinerario tenga un numero
representativo y defendible en la presentacion, no una tarifa real vigente.
Ajustar estos valores es una decision de producto, no un detalle tecnico:
documentar el cambio en docs/DECISIONES.md si se tocan.
"""

from __future__ import annotations

# Costo base estimado por categoria de atractivo (entrada, cuando el
# documento no trae rango_precio, que es lo mas comun en atractivos y menos
# en comercios curados).
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

COSTO_POR_DEFECTO = 5.0

# Mapeo de rango_precio (convencion "$".."$$$$") a costo estimado. Se usa
# cuando el documento (tipicamente curado a mano) trae rango_precio: manda
# sobre la tabla por categoria porque es un dato mas especifico del lugar.
COSTO_POR_RANGO_PRECIO: dict[str, float] = {
    "$": 10.0,
    "$$": 25.0,
    "$$$": 50.0,
    "$$$$": 100.0,
}


def estimar_costo(categoria: str | None, rango_precio: str | None) -> float:
    """rango_precio manda si esta presente (viene de datos curados a mano,
    mas confiable). Si no, se usa el costo base de la primera categoria de
    `categoria` (OpenTripMap trae varios kinds separados por coma, ej.
    "museums,historic": solo el primero define el costo, igual que ya
    define el nombre visible en normalizar.py). Si no hay ninguno de los
    dos, el costo por defecto."""
    if rango_precio and rango_precio in COSTO_POR_RANGO_PRECIO:
        return COSTO_POR_RANGO_PRECIO[rango_precio]
    categoria_primaria = categoria.split(",")[0].strip() if categoria else None
    if categoria_primaria and categoria_primaria in COSTO_BASE_POR_CATEGORIA:
        return COSTO_BASE_POR_CATEGORIA[categoria_primaria]
    return COSTO_POR_DEFECTO


# Gasto diario estimado por persona en USD (comida + transporte local),
# segun destino piloto y nivel de presupuesto declarado (RF1). Estimacion
# ilustrativa basada en el costo de vida general de cada ciudad para
# alguien que ya reservo alojamiento aparte (RF6): Barcelona y Miami son
# mas caras que Cancun en el segmento turistico. No sale de ninguna API en
# vivo, se documenta y se puede ajustar como decision de producto (D-19 en
# DECISIONES.md).
GASTO_DIARIO_POR_PERSONA: dict[str, dict[str, float]] = {
    "Barcelona": {"bajo": 30.0, "medio": 55.0, "alto": 110.0},
    "Miami": {"bajo": 35.0, "medio": 65.0, "alto": 130.0},
    "Cancun": {"bajo": 25.0, "medio": 45.0, "alto": 90.0},
}

GASTO_DIARIO_POR_DEFECTO = 40.0


def estimar_gasto_diario(destino: str | None, presupuesto: str | None) -> float:
    """Gasto diario por persona (comida + transporte local) segun destino
    y presupuesto. Si el destino no es piloto o el presupuesto no se
    declaro, usa GASTO_DIARIO_POR_DEFECTO en vez de fallar."""
    tabla_destino = GASTO_DIARIO_POR_PERSONA.get(destino or "", {})
    if presupuesto and presupuesto in tabla_destino:
        return tabla_destino[presupuesto]
    return GASTO_DIARIO_POR_DEFECTO
