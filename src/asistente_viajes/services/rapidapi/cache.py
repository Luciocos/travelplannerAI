"""Cache de resolucion de destinos para RapidAPI (RF6/RF7, D-06).

Ninguna de las dos APIs (Booking.com15, Fly Scraper) acepta un nombre de
ciudad como parametro de busqueda: primero hay que resolverlo a un id
propio de cada proveedor, y esa resolucion no cambia nunca para un mismo
destino. Sin este cache la cuota Free se quema en un par de dias de
desarrollo (ver migracion-amadeus-a-rapidapi.md, seccion 3.3).

Regla: toda resolucion de destino pasa por `buscar_destino_cacheado`
primero. Solo si no hay hit se llama a la API, y el resultado se guarda
con `guardar_destino_cacheado`.
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from asistente_viajes.services.rapidapi.models import DestinoResuelto
from asistente_viajes.texto import normalizar as normalizar_texto

SQL_BUSCAR = """
SELECT id_externo, tipo, payload
FROM destino_externo
WHERE proveedor = %(proveedor)s AND texto_consultado = %(texto_consultado)s;
"""

SQL_GUARDAR = """
INSERT INTO destino_externo (proveedor, texto_consultado, id_externo, tipo, payload)
VALUES (%(proveedor)s, %(texto_consultado)s, %(id_externo)s, %(tipo)s, %(payload)s)
ON CONFLICT (proveedor, texto_consultado)
DO UPDATE SET id_externo = EXCLUDED.id_externo, tipo = EXCLUDED.tipo, payload = EXCLUDED.payload;
"""


def buscar_destino_cacheado(
    conexion: psycopg.Connection, proveedor: str, texto_consultado: str
) -> DestinoResuelto | None:
    """None si no hay hit todavia, nunca sale a la red por su cuenta."""
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_BUSCAR,
            {"proveedor": proveedor, "texto_consultado": normalizar_texto(texto_consultado)},
        )
        fila = cursor.fetchone()

    if fila is None:
        return None

    id_externo, tipo, payload = fila
    return DestinoResuelto(
        proveedor=proveedor,
        texto_consultado=texto_consultado,
        id_externo=id_externo,
        tipo=tipo,
        nombre=payload.get("nombre", texto_consultado),
        pais=payload.get("pais"),
        lat=payload.get("lat"),
        lon=payload.get("lon"),
    )


def guardar_destino_cacheado(conexion: psycopg.Connection, destino: DestinoResuelto) -> None:
    """Idempotente: un mismo (proveedor, texto_consultado) se actualiza, no duplica."""
    payload = {
        "nombre": destino.nombre,
        "pais": destino.pais,
        "lat": destino.lat,
        "lon": destino.lon,
    }
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_GUARDAR,
            {
                "proveedor": destino.proveedor,
                "texto_consultado": normalizar_texto(destino.texto_consultado),
                "id_externo": destino.id_externo,
                "tipo": destino.tipo,
                "payload": Jsonb(payload),
            },
        )
