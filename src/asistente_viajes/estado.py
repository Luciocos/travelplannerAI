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

# D-14: el orquestador pide todo lo que falta en una sola pregunta
# consolidada (con opciones y una sugerencia por campo), no de a 2 por
# turno como preveia el diseño original (arquitectura.md). Se mantiene la
# constante por compatibilidad de nombres en el codigo existente, pero ya
# no limita cuantos slots se piden por turno.
MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO = 2

DURACION_MAXIMA_DIAS = 21
CANTIDAD_PERSONAS_MAXIMA = 20

# Sinonimos habituales de presupuesto que un usuario puede escribir, hacia
# el vocabulario fijo bajo/medio/alto que usan costos.py y las preguntas
# dirigidas. No es un mapeo de "adivinar" un valor no dicho (eso violaria
# la regla de nada inventado): solo normaliza como el usuario nombro un
# valor que si dijo, de forma explicita.
_SINONIMOS_PRESUPUESTO = {
    "economico": "bajo",
    "barato": "bajo",
    "ajustado": "bajo",
    "moderado": "medio",
    "intermedio": "medio",
    "lujo": "alto",
    "lujoso": "alto",
    "alto gama": "alto",
}


class PreferenciasViaje(BaseModel):
    destino: str | None = None
    tipo_destino: str | None = None
    intereses: list[str] | None = None
    presupuesto: str | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    cantidad_personas: int | None = None
    # Nuevos (Fase 7C): origen para RF7 (vuelos), duracion_dias para poder
    # armar un plan de "7 dias, fecha a confirmar" sin fechas de calendario
    # exactas (D-14).
    origen: str | None = None
    duracion_dias: int | None = None

    def tiene_cuando(self) -> bool:
        """El 'cuando' del viaje esta resuelto si hay fechas exactas o, al
        menos, una duracion en dias (D-14: un plan no tiene por que esperar
        fechas de calendario concretas)."""
        return (self.fecha_inicio is not None and self.fecha_fin is not None) or (
            self.duracion_dias is not None
        )

    def slots_faltantes(self) -> list[str]:
        """Slots obligatorios que todavia no tienen valor, en el orden de
        SLOTS_OBLIGATORIOS. intereses cuenta como faltante si es None o una
        lista vacia. tipo_destino deja de ser obligatorio en cuanto hay
        destino: se deriva de destinos.json (D-14), no tiene sentido
        preguntarlo aparte para un destino piloto ya confirmado. fecha_inicio
        y fecha_fin cuentan como resueltas si hay duracion_dias en su
        lugar (ver tiene_cuando)."""
        faltantes = []
        for nombre in SLOTS_OBLIGATORIOS:
            if nombre == "tipo_destino" and self.destino is not None:
                continue
            if nombre in ("fecha_inicio", "fecha_fin"):
                if not self.tiene_cuando():
                    faltantes.append(nombre)
                continue
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


def normalizar_presupuesto(valor: str | None) -> str | None:
    """Mapea sinonimos habituales ('economico', 'lujo'...) al vocabulario
    fijo bajo/medio/alto. No inventa un presupuesto que el usuario no dijo,
    solo normaliza la palabra que si uso."""
    if valor is None:
        return None
    normalizado = valor.strip().lower()
    return _SINONIMOS_PRESUPUESTO.get(normalizado, normalizado)


def validar_preferencias(estado: PreferenciasViaje, hoy: date) -> list[str]:
    """Validaciones deterministicas (nunca las decide el LLM): fechas
    pasadas, fin antes que inicio, viajes mas largos que
    DURACION_MAXIMA_DIAS, y cantidad_personas fuera de rango. Devuelve una
    lista de mensajes en espanol listos para mostrarle al usuario; lista
    vacia si esta todo bien. No corrige nada solo, para no inventar un dato
    distinto del que el usuario dio."""
    errores: list[str] = []

    if estado.fecha_inicio is not None and estado.fecha_inicio < hoy:
        errores.append(
            f"La fecha de inicio ({estado.fecha_inicio.strftime('%d/%m/%Y')}) ya paso. "
            "¿Me confirma la fecha correcta?"
        )
    if (
        estado.fecha_inicio is not None
        and estado.fecha_fin is not None
        and estado.fecha_fin < estado.fecha_inicio
    ):
        errores.append("La fecha de fin es anterior a la de inicio. ¿Me confirma las fechas?")

    duracion = None
    if estado.fecha_inicio is not None and estado.fecha_fin is not None:
        duracion = (estado.fecha_fin - estado.fecha_inicio).days + 1
    elif estado.duracion_dias is not None:
        duracion = estado.duracion_dias

    if duracion is not None and duracion > DURACION_MAXIMA_DIAS:
        errores.append(
            f"Por ahora armo itinerarios de hasta {DURACION_MAXIMA_DIAS} dias. "
            "¿Le parece si acortamos el viaje o lo dividimos en dos consultas?"
        )

    if estado.cantidad_personas is not None and not (
        1 <= estado.cantidad_personas <= CANTIDAD_PERSONAS_MAXIMA
    ):
        errores.append(
            f"La cantidad de personas tiene que estar entre 1 y {CANTIDAD_PERSONAS_MAXIMA}. "
            "¿Me confirma cuantos viajan?"
        )

    return errores


# Campos del estado que, si cambian, invalidan un plan ya armado (RF5) y
# ameritan re-armarlo solo en vez de esperar a que el usuario lo pida de
# nuevo (D-14, ver grafo.py).
CAMPOS_QUE_AFECTAN_EL_PLAN = (
    "destino",
    "fecha_inicio",
    "fecha_fin",
    "duracion_dias",
    "cantidad_personas",
    "presupuesto",
    "intereses",
)


def detectar_cambios(anterior: PreferenciasViaje, nuevo: PreferenciasViaje) -> set[str]:
    """Campos de CAMPOS_QUE_AFECTAN_EL_PLAN cuyo valor cambio entre dos
    estados. Se usa para decidir si un plan ya armado quedo desactualizado
    (ver grafo.py, D-14)."""
    cambiados = set()
    for campo in CAMPOS_QUE_AFECTAN_EL_PLAN:
        if getattr(anterior, campo) != getattr(nuevo, campo):
            cambiados.add(campo)
    return cambiados
