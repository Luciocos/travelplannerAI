"""Tool de LangChain: armar_plan (RF5, nucleo, Fase 6).

Itinerario dia a dia con 2 o 3 actividades reales por dia, agrupadas por
cercania geografica, y costo estimado. El LLM no participa en esta tool:
el costo sale de costos.py (tabla fija por categoria/rango_precio mas gasto
diario estimado por presupuesto), nunca de un numero generado por el
modelo. Es logica de negocio determinista sobre lo que ya recupero el RAG,
no generacion (util para la defensa: no todo el sistema es RAG+LLM).

Persiste en `itinerario` e `itinerario_item` (sql/001_schema.sql).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from asistente_viajes import ajustes as ajustes_plan
from asistente_viajes.costos import estimar_costo, estimar_gasto_diario
from asistente_viajes.estado import PreferenciasViaje
from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.recuperacion.atractivos import buscar_atractivos

ACTIVIDADES_POR_DIA_MIN = 2
ACTIVIDADES_POR_DIA_MAX = 3

NOMBRE_DIA_LIBRE = "Dia libre para explorar por su cuenta"
NOMBRE_DIA_LIBRE_A_PEDIDO = "Dia libre, sin actividades programadas"

SQL_INSERTAR_ITINERARIO = """
INSERT INTO itinerario (destino, fecha_inicio, fecha_fin, cantidad_personas, presupuesto, costo_estimado)
VALUES (%(destino)s, %(fecha_inicio)s, %(fecha_fin)s, %(cantidad_personas)s, %(presupuesto)s, %(costo_estimado)s)
RETURNING id;
"""

SQL_INSERTAR_ITEM = """
INSERT INTO itinerario_item (itinerario_id, dia, orden, documento_id, descripcion, costo_estimado)
VALUES (%(itinerario_id)s, %(dia)s, %(orden)s, %(documento_id)s, %(descripcion)s, %(costo_estimado)s);
"""


class ErrorFechasIncompletas(ValueError):
    """El estado no tiene fechas exactas ni duracion_dias: armar_plan no
    puede decidir cuantos dias armar. El orquestador (Step 5) lo captura y
    responde pidiendo el dato en vez de dejar que la excepcion llegue cruda
    al usuario."""


class ActividadDelPlan(BaseModel):
    documento_id: int | None = None
    nombre: str | None
    categoria: str | None
    costo_estimado: float
    lat: float | None = None
    lon: float | None = None


class DiaDelPlan(BaseModel):
    dia: int
    fecha: date | None = None
    actividades: list[ActividadDelPlan]
    costo_actividades: float
    gasto_estimado_dia: float
    costo_dia: float


class PlanDeViaje(BaseModel):
    destino: str
    moneda: str = "USD"
    dias: list[DiaDelPlan]
    costo_actividades_total: float
    gasto_estimado_total: float
    costo_total_estimado: float
    cantidad_personas: int
    costo_total_grupo: float
    supuestos: list[str] = Field(default_factory=list)
    # Fase 7E (D-22): que pidio el cliente que se pudo aplicar y que no.
    # Lo consume la redaccion (ver PROMPT_REDACTAR) para acusar recibo o
    # admitir el limite con sus propias palabras.
    ajustes_aplicados: list[str] = Field(default_factory=list)
    ajustes_no_aplicados: list[str] = Field(default_factory=list)


class ArgsArmarPlan(BaseModel):
    estado: PreferenciasViaje = Field(
        description="Preferencias del viaje ya completas: destino, fechas (o duracion_dias) y cantidad de personas"
    )


def _cantidad_dias(estado: PreferenciasViaje) -> int:
    """Numero de dias del plan a partir de fechas exactas o, si no hay,
    duracion_dias (D-14: un plan puede armarse sin fecha de calendario)."""
    if estado.fecha_inicio is not None and estado.fecha_fin is not None:
        return max((estado.fecha_fin - estado.fecha_inicio).days + 1, 1)
    if estado.duracion_dias is not None:
        return max(estado.duracion_dias, 1)
    raise ErrorFechasIncompletas(
        "Necesito fechas exactas o al menos la cantidad de dias del viaje para armar el plan."
    )


def _distancia_km(a: ResultadoRecuperado, b: ResultadoRecuperado) -> float:
    """Distancia aproximada entre dos puntos (formula haversine), en km."""
    radio_tierra_km = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, b.lat, a.lon, b.lon))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    formula = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radio_tierra_km * math.asin(math.sqrt(formula))


def _ordenar_por_cercania(candidatos: list[ResultadoRecuperado]) -> list[ResultadoRecuperado]:
    """Tour greedy de vecino mas cercano sobre los candidatos con
    coordenadas: cada parada siguiente es la mas cercana a la anterior
    todavia sin visitar. Agrupar el itinerario dia a dia sobre esta ruta
    (en vez del orden de similitud semantica) evita que un mismo dia salte
    de punta a punta del destino."""
    if not candidatos:
        return []
    restantes = list(candidatos)
    ruta = [restantes.pop(0)]
    while restantes:
        ultimo = ruta[-1]
        siguiente = min(restantes, key=lambda c: _distancia_km(ultimo, c))
        restantes.remove(siguiente)
        ruta.append(siguiente)
    return ruta


def _candidatos_en_orden_de_visita(
    candidatos: list[ResultadoRecuperado],
) -> list[ResultadoRecuperado]:
    """Con coordenadas primero (ordenados por cercania geografica), sin
    coordenadas al final (no se pueden agrupar, ver plan de fases 7C)."""
    con_coords = [c for c in candidatos if c.lat is not None and c.lon is not None]
    sin_coords = [c for c in candidatos if c not in con_coords]
    return _ordenar_por_cercania(con_coords) + sin_coords


def _repartir_por_dia(
    candidatos: list[ResultadoRecuperado],
    dias_totales: int,
    libres: set[int] | None = None,
    por_dia_max: int = ACTIVIDADES_POR_DIA_MAX,
) -> list[list[ResultadoRecuperado]]:
    """2 o 3 actividades reales por dia (o las que pidio el cliente), sin
    repetir, mas actividades por delante en los primeros dias para no dejar
    un ultimo dia vacio.

    Los dias en `libres` quedan con una lista vacia a proposito (el cliente
    los pidio sin actividades, ver ajustes.py) y no consumen candidatos: lo
    que les hubiera tocado se reparte entre los demas dias, en vez de
    perderse."""
    libres = libres or set()
    por_dia_min = min(ACTIVIDADES_POR_DIA_MIN, por_dia_max)
    ordenados = _candidatos_en_orden_de_visita(candidatos)
    grupos: list[list[ResultadoRecuperado]] = []
    indice = 0
    for numero_dia in range(1, dias_totales + 1):
        if numero_dia in libres:
            grupos.append([])
            continue

        dias_con_actividades_despues = len(
            [d for d in range(numero_dia + 1, dias_totales + 1) if d not in libres]
        )
        restantes_para_dias_futuros = dias_con_actividades_despues * por_dia_min
        cantidad_hoy = por_dia_max
        if len(ordenados) - indice - cantidad_hoy < restantes_para_dias_futuros:
            cantidad_hoy = por_dia_min

        grupo = ordenados[indice : indice + cantidad_hoy]
        indice += len(grupo)
        grupos.append(grupo)
    return grupos


def _actividad_dia_libre(a_pedido: bool = False) -> ActividadDelPlan:
    """El dia sin actividades. `a_pedido` distingue las dos razones por las
    que un dia puede quedar libre, que para el cliente no son lo mismo: o lo
    pidio el (y hay que confirmarselo), o el corpus se quedo sin candidatos
    reales (y hay que ser honesto al respecto, ver P-08)."""
    nombre = NOMBRE_DIA_LIBRE_A_PEDIDO if a_pedido else NOMBRE_DIA_LIBRE
    return ActividadDelPlan(documento_id=None, nombre=nombre, categoria=None, costo_estimado=0.0)


def _armar_dias(
    candidatos: list[ResultadoRecuperado],
    dias_totales: int,
    fecha_inicio: date | None,
    gasto_diario: float,
    libres: set[int] | None = None,
    por_dia_max: int = ACTIVIDADES_POR_DIA_MAX,
) -> list[DiaDelPlan]:
    libres = libres or set()
    dias: list[DiaDelPlan] = []
    grupos = _repartir_por_dia(candidatos, dias_totales, libres, por_dia_max)
    for indice_dia, grupo in enumerate(grupos):
        numero_dia = indice_dia + 1
        actividades = [
            ActividadDelPlan(
                documento_id=resultado.id,
                nombre=resultado.nombre,
                categoria=resultado.categoria,
                costo_estimado=estimar_costo(resultado.categoria, resultado.rango_precio),
                lat=resultado.lat,
                lon=resultado.lon,
            )
            for resultado in grupo
        ]
        if not actividades:
            # Nunca un dia vacio: o el cliente lo pidio libre (D-22), o el
            # corpus se quedo sin candidatos reales y se lo decimos
            # honestamente en vez de mostrar un hueco (ver P-08).
            actividades = [_actividad_dia_libre(a_pedido=numero_dia in libres)]

        costo_actividades = sum(actividad.costo_estimado for actividad in actividades)
        fecha = fecha_inicio + timedelta(days=indice_dia) if fecha_inicio is not None else None
        dias.append(
            DiaDelPlan(
                dia=numero_dia,
                fecha=fecha,
                actividades=actividades,
                costo_actividades=costo_actividades,
                gasto_estimado_dia=gasto_diario,
                costo_dia=costo_actividades + gasto_diario,
            )
        )
    return dias


def armar_plan(conexion: psycopg.Connection, estado: PreferenciasViaje) -> PlanDeViaje:
    """Logica pura de la tool, sin el decorador. Asume que `estado` ya
    tiene destino y cantidad_personas (RF11 se encarga de eso antes de
    llegar aca, no se valida de nuevo); fechas exactas o duracion_dias son
    obligatorias aca, si faltan las dos levanta ErrorFechasIncompletas en
    vez de un TypeError crudo."""
    dias_totales = _cantidad_dias(estado)
    intereses = estado.intereses or []
    ajustes = estado.ajustes_activos()

    libres = ajustes_plan.dias_libres(ajustes, dias_totales)
    por_dia_max = ajustes_plan.actividades_por_dia(ajustes, ACTIVIDADES_POR_DIA_MAX)
    dias_con_actividades = dias_totales - len(libres)

    # Se piden candidatos solo para los dias que van a tener actividades, y
    # de mas, porque la exclusion filtra despues de recuperar (el filtro es
    # sobre texto del cliente, no algo que se pueda pasar al SQL del RAG).
    candidatos = buscar_atractivos(
        conexion,
        destino=estado.destino,
        intereses=intereses,
        k=max(dias_con_actividades, 1) * por_dia_max * 2,
    )
    candidatos = [
        candidato
        for candidato in candidatos
        if not ajustes_plan.excluye(ajustes, candidato.nombre, candidato.categoria)
    ]

    gasto_diario = estimar_gasto_diario(estado.destino, estado.presupuesto)
    dias = _armar_dias(
        candidatos, dias_totales, estado.fecha_inicio, gasto_diario, libres, por_dia_max
    )

    costo_actividades_total = sum(dia.costo_actividades for dia in dias)
    gasto_estimado_total = sum(dia.gasto_estimado_dia for dia in dias)
    costo_total = costo_actividades_total + gasto_estimado_total
    cantidad_personas = estado.cantidad_personas or 1

    supuestos = []
    if estado.presupuesto is None:
        supuestos.append("presupuesto no indicado, se uso un gasto diario de referencia")
    if estado.fecha_inicio is None:
        supuestos.append("sin fecha de inicio confirmada, el plan es por cantidad de dias")

    # Que se aplico y que no. Esto es lo que despues le permite a la
    # redaccion acusar recibo de verdad ("le deje el dia 6 libre") o admitir
    # el limite ("eso no lo puedo aplicar"), en vez de devolver el mismo
    # plan en silencio, que es el bug que origino todo esto (P-14).
    aplicados = [
        descripcion
        for ajuste in ajustes
        if (descripcion := ajustes_plan.describir(ajuste, dias_totales))
    ]
    no_aplicados = [
        ajuste.pedido_original or "un pedido sobre el plan"
        for ajuste in ajustes_plan.ajustes_no_aplicables(ajustes)
    ]
    for fuera_de_rango in ajustes_plan.dias_fuera_de_rango(ajustes, dias_totales):
        no_aplicados.append(
            f"{fuera_de_rango.pedido_original or 'dejar un dia libre'} "
            f"(el plan tiene {dias_totales} dia(s))"
        )
    supuestos.extend(aplicados)

    return PlanDeViaje(
        destino=estado.destino,
        dias=dias,
        ajustes_aplicados=aplicados,
        ajustes_no_aplicados=no_aplicados,
        costo_actividades_total=costo_actividades_total,
        gasto_estimado_total=gasto_estimado_total,
        costo_total_estimado=costo_total,
        cantidad_personas=cantidad_personas,
        costo_total_grupo=costo_total * cantidad_personas,
        supuestos=supuestos,
    )


def guardar_itinerario(
    conexion: psycopg.Connection, estado: PreferenciasViaje, plan: PlanDeViaje
) -> int:
    """Persiste el plan en itinerario/itinerario_item. Devuelve el id del
    itinerario creado."""
    with conexion.cursor() as cursor:
        cursor.execute(
            SQL_INSERTAR_ITINERARIO,
            {
                "destino": estado.destino,
                "fecha_inicio": estado.fecha_inicio,
                "fecha_fin": estado.fecha_fin,
                "cantidad_personas": plan.cantidad_personas,
                "presupuesto": estado.presupuesto,
                "costo_estimado": plan.costo_total_estimado,
            },
        )
        (itinerario_id,) = cursor.fetchone()

        for dia in plan.dias:
            for orden, actividad in enumerate(dia.actividades, start=1):
                cursor.execute(
                    SQL_INSERTAR_ITEM,
                    {
                        "itinerario_id": itinerario_id,
                        "dia": dia.dia,
                        "orden": orden,
                        "documento_id": actividad.documento_id,
                        "descripcion": actividad.nombre or "Actividad sin nombre",
                        "costo_estimado": actividad.costo_estimado,
                    },
                )
    return itinerario_id


def resumen_markdown(plan: PlanDeViaje) -> str:
    """Version "documento" del plan (titulo, sin el tono conversacional
    del mensaje de chat de grafo.py._resumen_plan) para el boton de
    descarga de la UI (ui/servicio.py)."""
    lineas = [f"# Plan de viaje: {plan.destino}", ""]
    for dia in plan.dias:
        nombres = ", ".join(a.nombre or "actividad sin nombre" for a in dia.actividades)
        etiqueta = f"Día {dia.dia}" + (f" ({dia.fecha.strftime('%d/%m')})" if dia.fecha else "")
        lineas.append(f"- **{etiqueta}**: {nombres} (costo estimado ${dia.costo_dia:.0f})")
    lineas.append("")
    lineas.append(
        f"**Costo total estimado**: {plan.moneda} {plan.costo_total_estimado:.0f} por persona, "
        f"{plan.moneda} {plan.costo_total_grupo:.0f} para el grupo de {plan.cantidad_personas}."
    )
    if plan.supuestos:
        lineas.append("")
        lineas.append("_" + "; ".join(plan.supuestos) + "._")
    return "\n".join(lineas)


def crear_tool_armar_plan(conexion: psycopg.Connection):
    """Arma la tool de LangChain, con la conexion ya inyectada."""

    @tool("armar_plan", args_schema=ArgsArmarPlan)
    def _tool(estado: PreferenciasViaje) -> dict:
        """Arma un itinerario dia a dia para un viaje ya completo (destino,
        fechas o duracion en dias, y cantidad de personas conocidos), con
        2 o 3 actividades reales por dia agrupadas por cercania y un costo
        estimado total. Usar esta tool cuando el usuario pida el plan o
        itinerario completo del viaje, no para consultas puntuales de una
        sola actividad o recomendacion."""
        plan = armar_plan(conexion, estado)
        guardar_itinerario(conexion, estado, plan)
        return plan.model_dump()

    return _tool
