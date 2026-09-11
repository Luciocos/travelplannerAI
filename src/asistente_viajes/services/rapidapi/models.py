"""Modelos normalizados de RF6/RF7 (alojamiento y vuelos, RapidAPI).

La forma cruda de Booking.com15 y Fly Scraper no puede llegar al agente:
son wrappers no oficiales, con estructuras distintas para lo mismo, y
pueden cambiar sin aviso. Cada adaptador (`booking.py`, `fly_scraper.py`)
tiene una funcion `_a_modelo` que es el unico lugar del proyecto que
conoce la forma cruda de esa API.

Todos los campos son opcionales salvo el nombre y el proveedor: los
wrappers omiten campos con frecuencia y un dato faltante no puede
tumbar la tool (ver migracion-amadeus-a-rapidapi.md, seccion 3.2).
"""

from __future__ import annotations

from pydantic import BaseModel


class DestinoResuelto(BaseModel):
    proveedor: str  # "booking" | "fly_scraper"
    texto_consultado: str
    id_externo: str
    tipo: str | None = None  # search_type en Booking: "CITY", "REGION", "district"...
    nombre: str
    pais: str | None = None
    lat: float | None = None
    lon: float | None = None


class Alojamiento(BaseModel):
    nombre: str
    proveedor: str
    precio_total: float | None = None
    moneda: str | None = None
    puntaje: float | None = None  # escala 0-10
    cantidad_resenias: int | None = None
    direccion: str | None = None
    url_imagen: str | None = None
    es_fixture: bool = False


class OpcionVuelo(BaseModel):
    proveedor: str
    origen: str | None = None  # IATA
    destino: str | None = None  # IATA
    fecha_salida: str | None = None  # ISO
    fecha_regreso: str | None = None
    precio_total: float | None = None
    moneda: str | None = None
    aerolineas: list[str] = []
    escalas: int | None = None
    duracion_minutos: int | None = None
    es_fixture: bool = False
