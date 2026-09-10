"""Estado de la conversacion: preferencias del viaje en curso (RF11).

PreferenciasViaje tiene todos los campos opcionales porque se completa de
a poco, turno a turno. La regla que importa es la de fusionar_preferencias:
el merge es no destructivo, un slot ya cargado nunca se pisa con None.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

SLOTS_OBLIGATORIOS = (
    "destino",
    "tipo_destino",
    "intereses",
    "presupuesto",
    "fecha_inicio",
    "fecha_fin",
    "cantidad_personas",
)

MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO = 2


class PreferenciasViaje(BaseModel):
    destino: str | None = None
    tipo_destino: str | None = None
    intereses: list[str] | None = None
    presupuesto: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    cantidad_personas: int | None = None

    def slots_faltantes(self) -> list[str]:
        """Slots obligatorios que todavia no tienen valor, en el orden de
        SLOTS_OBLIGATORIOS. intereses cuenta como faltante si es None o
        una lista vacia."""
        faltantes = []
        for nombre in SLOTS_OBLIGATORIOS:
            valor = getattr(self, nombre)
            if valor is None or (nombre == "intereses" and not valor):
                faltantes.append(nombre)
        return faltantes

    def completo(self) -> bool:
        return not self.slots_faltantes()


def fusionar_preferencias(
    actual: PreferenciasViaje, nuevas: PreferenciasViaje
) -> PreferenciasViaje:
    """Merge no destructivo (RF2): un slot ya cargado en `actual` nunca se
    pisa con None de `nuevas`. Si `nuevas` trae un valor, ese valor gana.
    """
    datos_actuales = actual.model_dump()
    datos_nuevos = nuevas.model_dump()

    fusionado = {
        campo: (datos_nuevos[campo] if datos_nuevos[campo] is not None else datos_actuales[campo])
        for campo in datos_actuales
    }
    return PreferenciasViaje(**fusionado)
