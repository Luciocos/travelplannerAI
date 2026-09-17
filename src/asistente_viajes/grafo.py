"""Orquestador del asistente de viajes (RF11, RF12, Fase 7C).

Implementado como un grafo de LangGraph (D-12, redefine D-08): cada turno
pasa por nodos con responsabilidad unica en vez de una sola llamada de
clasificacion. El diseño anterior (D-08/D-10, un LLM que elegia UNA tool
por turno mirando solo el mensaje actual) no podia atender mas de un
pedido por mensaje, ni contestar algo que ya sabia (el destino elegido,
por que se le agradecio), porque no tenia mas contexto que ese mensaje.

Flujo (ver tambien construir_grafo().get_graph().draw_mermaid()):

    interpretar -> actualizar_estado -> planificar -> ejecutar_acciones
        -> disparar_info_destino -> redactar

- interpretar: UN llamado estructurado al LLM que extrae los datos del
  viaje Y decide que acciones pidio el cliente (armar_plan,
  recomendar_actividades, recomendar_locales, responder_faq_viajero;
  puede ser mas de una por turno). Extraccion deliberadamente permisiva
  (fechas como texto, no como `date`): un formato de fecha invalido del
  LLM nunca puede tirar abajo el llamado estructurado completo con un
  ValidationError, se descarta despues en actualizar_estado.
- actualizar_estado: logica pura, nunca el LLM. Parsea las fechas de
  texto a `date` (en silencio si no puede), fusiona contra el estado
  (RF2, merge no destructivo), y detecta si el cliente nombro un destino
  que no es piloto.
- planificar: logica pura. Decide que ejecutar este turno: si falta
  algun dato obligatorio, una pregunta consolidada (D-14) mas, si ya hay
  destino, una recomendacion barata de regalo (nunca se deja al cliente
  solo con la pregunta); si el plan ya armado quedo desactualizado por
  un cambio de dato (ver estado.detectar_cambios), se re-arma solo; las
  acciones que pidio el cliente se agregan si sus precondiciones estan
  cubiertas.
- ejecutar_acciones: corre cada accion pendiente en un solo nodo, con un
  loop de Python (no un nodo de grafo por tool: ver D-12, mismo
  criterio de arquitectura.md de no complicar el flujo mas de lo que
  hace falta). Cada accion esta envuelta en su propio try/except: si una
  falla, esa accion se reporta como error puntual y las demas se
  ejecutan igual (antes, pedir el plan sin fechas tiraba un TypeError
  crudo que mataba todo procesar_mensaje).
- disparar_info_destino: unica excepcion a que decida el LLM (RF12), se
  dispara sola la primera vez que el destino queda confirmado con
  fechas, y de nuevo si el destino cambia a mitad de conversacion (antes
  no se volvia a disparar nunca mas en toda la sesion).
- redactar: si ejecutar_acciones no genero nada (el cliente no pidio
  ninguna accion ni le faltaba ningun dato: un saludo, un agradecimiento,
  una pregunta sobre algo que ya se hablo), UN llamado al LLM responde
  desde el historial y el estado (ver PROMPT_CONVERSAR). Si genero algo,
  se concatenan los fragmentos sin otro llamado al LLM: cada tool ya
  devuelve su texto redactado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

import psycopg
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from asistente_viajes.destinos import blurb_caracteristicas_destinos, buscar_destino_piloto
from asistente_viajes.estado import (
    PreferenciasViaje,
    detectar_cambios,
    fusionar_preferencias,
    normalizar_presupuesto,
    validar_preferencias,
)
from asistente_viajes.llm import RotadorClavesGemini, contenido_texto
from asistente_viajes.preguntas import (
    armar_pregunta_consolidada,
    destinos_piloto_destacados,
    tipo_destino_de,
    valores_sugeridos,
)
from asistente_viajes.prompts import PROMPT_CONVERSAR, PROMPT_INTERPRETAR_TURNO
from asistente_viajes.services.cambio import convertir_desde_usd
from asistente_viajes.services.rapidapi.booking import buscar_alojamiento, buscar_vuelos
from asistente_viajes.services.rapidapi.models import Alojamiento, OpcionVuelo
from asistente_viajes.tools.armar_plan import (
    ErrorFechasIncompletas,
    PlanDeViaje,
    armar_plan,
    guardar_itinerario,
)
from asistente_viajes.tools.info_destino import info_destino
from asistente_viajes.tools.recomendar_actividades import (
    ActividadRecomendada,
    recomendar_actividades,
)
from asistente_viajes.tools.recomendar_locales import LocalRecomendado, recomendar_locales
from asistente_viajes.tools.responder_faq_viajero import responder_faq_viajero

logger = logging.getLogger(__name__)

TipoAccion = Literal[
    "armar_plan",
    "recomendar_actividades",
    "recomendar_locales",
    "responder_faq_viajero",
    "buscar_alojamiento",
    "buscar_vuelos",
    "convertir_moneda",
]

MONEDA_DESTINO_DEFECTO = "ARS"  # el publico de este TP es de Argentina

MAXIMO_FRAGMENTOS_POR_TURNO = 4
CANTIDAD_RESULTADOS_DEFECTO = 3
TURNOS_DE_HISTORIAL = 8

# Los usuarios de este TP son de Argentina; "hoy" para interpretar fechas
# relativas ("la semana que viene") se calcula en su huso horario, no en
# UTC del servidor (a la noche, UTC ya cambio de dia).
ZONA_HORARIA_USUARIOS = ZoneInfo("America/Argentina/Buenos_Aires")


def _hoy_argentina() -> date:
    return datetime.now(tz=ZONA_HORARIA_USUARIOS).date()


class AccionPedida(BaseModel):
    tipo: TipoAccion
    cantidad_resultados: int | None = None
    # Solo para recomendar_locales/responder_faq_viajero: el fragmento del
    # mensaje relevante para ESTA accion en particular. Si el mensaje pide
    # varias cosas a la vez ("armame el plan, decime donde comer y si es
    # seguro de noche"), pasar el mensaje completo como consulta de cada
    # accion diluye la busqueda semantica de cada una. None si el mensaje
    # ya es una sola consulta (se usa el mensaje completo en ese caso).
    consulta: str | None = None
    # Solo para convertir_moneda: codigo ISO de la moneda pedida (ej.
    # "ARS", "EUR"). Si el cliente no la menciona, se usa MONEDA_DESTINO_DEFECTO.
    moneda_destino: str | None = None


class InterpretacionTurno(BaseModel):
    """Salida estructurada de `interpretar`. Fechas como texto (no como
    `date`) a proposito: si el LLM devuelve un formato invalido, mejor
    ignorarlo en actualizar_estado que tirar abajo el llamado
    estructurado entero con un ValidationError."""

    destino: str | None = None
    destino_fuera_de_alcance: str | None = None
    intereses: list[str] | None = None
    presupuesto: str | None = None
    fecha_inicio: str | None = None
    fecha_fin: str | None = None
    duracion_dias: int | None = None
    cantidad_personas: int | None = None
    origen: str | None = None  # ciudad de salida, solo relevante para buscar_vuelos (RF7)
    usar_sugerencias: bool = False
    acciones: list[AccionPedida] = Field(default_factory=list)


@dataclass
class ContextoGrafo:
    """Dependencias inyectadas via runtime context de LangGraph (no
    config["configurable"]): conexion y rotador se resuelven una vez por
    turno, hoy se centraliza aca para no tener `datetime.now()` repartido
    (y para poder fijarlo en los tests)."""

    conexion: psycopg.Connection
    rotador: RotadorClavesGemini
    hoy: date


class Fragmento(TypedDict):
    tipo: str
    texto: str


class EstadoGrafo(TypedDict):
    mensaje: str
    historial: list[dict]
    estado: dict
    estado_anterior: dict
    ultimo_plan: dict | None
    info_destino_mostrada_para: str | None
    interpretacion: dict | None
    destino_no_soportado: str | None
    acciones_pedidas: list[dict]
    pendientes: list[dict]
    fragmentos: list[Fragmento]
    respuesta_texto: str


def _parsear_fecha(texto: str | None) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        logger.warning("no se pudo interpretar la fecha '%s', se ignora", texto)
        return None


def _historial_como_texto(historial: list[dict]) -> str:
    if not historial:
        return "(sin turnos previos)"
    turnos = historial[-TURNOS_DE_HISTORIAL:]
    return "\n".join(f"{turno['rol']}: {turno['texto']}" for turno in turnos)


def nodo_interpretar(estado_grafo: EstadoGrafo) -> dict:
    runtime = get_runtime(ContextoGrafo)
    estado_actual = PreferenciasViaje(**estado_grafo["estado"])
    prompt = PROMPT_INTERPRETAR_TURNO.format(
        destinos_piloto=blurb_caracteristicas_destinos(),
        fecha_hoy=runtime.context.hoy.isoformat(),
        historial=_historial_como_texto(estado_grafo["historial"]),
        estado_actual=estado_actual.model_dump(),
        mensaje=estado_grafo["mensaje"],
    )
    try:
        modelo_estructurado = runtime.context.rotador.con_salida_estructurada(InterpretacionTurno)
        interpretacion = modelo_estructurado.invoke(prompt)
    except Exception:
        logger.exception("fallo interpretar, se sigue el turno sin datos ni acciones nuevas")
        interpretacion = InterpretacionTurno()
    return {"interpretacion": interpretacion.model_dump()}


def nodo_actualizar_estado(estado_grafo: EstadoGrafo) -> dict:
    runtime = get_runtime(ContextoGrafo)
    interpretacion = InterpretacionTurno(**estado_grafo["interpretacion"])
    estado_actual = PreferenciasViaje(**estado_grafo["estado"])

    extraidos = PreferenciasViaje(
        destino=interpretacion.destino,
        intereses=interpretacion.intereses,
        presupuesto=normalizar_presupuesto(interpretacion.presupuesto),
        fecha_inicio=_parsear_fecha(interpretacion.fecha_inicio),
        fecha_fin=_parsear_fecha(interpretacion.fecha_fin),
        duracion_dias=interpretacion.duracion_dias,
        cantidad_personas=interpretacion.cantidad_personas,
        origen=interpretacion.origen,
    )
    fusionado = fusionar_preferencias(estado_actual, extraidos)

    if fusionado.tipo_destino is None:
        derivado = tipo_destino_de(fusionado.destino)
        if derivado is not None:
            fusionado = fusionado.model_copy(update={"tipo_destino": derivado})

    if interpretacion.usar_sugerencias:
        sugerencias = valores_sugeridos(fusionado.slots_faltantes())
        if sugerencias:
            fusionado = fusionar_preferencias(fusionado, PreferenciasViaje(**sugerencias))

    errores = validar_preferencias(fusionado, runtime.context.hoy)
    if errores:
        logger.info("validacion de preferencias encontro observaciones: %s", errores)

    return {
        "estado": fusionado.model_dump(mode="json"),
        "estado_anterior": estado_grafo["estado"],
        "destino_no_soportado": (
            interpretacion.destino_fuera_de_alcance if fusionado.destino is None else None
        ),
        "acciones_pedidas": [accion.model_dump() for accion in interpretacion.acciones],
    }


def nodo_planificar(estado_grafo: EstadoGrafo) -> dict:
    estado = PreferenciasViaje(**estado_grafo["estado"])
    estado_anterior = PreferenciasViaje(**estado_grafo["estado_anterior"])
    faltantes = estado.slots_faltantes()
    pendientes: list[dict] = []

    if estado_grafo.get("destino_no_soportado"):
        pendientes.append({"tipo": "destino_no_soportado"})

    if faltantes:
        pendientes.append({"tipo": "pedir_datos"})
        if estado.destino:
            # Nunca se deja al cliente solo con la pregunta: si ya hay
            # destino, se suma algo util en el mismo turno.
            pendientes.append({"tipo": "recomendar_actividades", "cantidad_resultados": 3})

    for accion in estado_grafo["acciones_pedidas"]:
        tipo = accion["tipo"]
        if any(p["tipo"] == tipo for p in pendientes):
            continue
        if tipo == "armar_plan" and (faltantes or not estado.tiene_cuando()):
            continue
        if tipo != "armar_plan" and not estado.destino:
            continue
        if tipo in ("buscar_alojamiento", "buscar_vuelos") and not (
            estado.fecha_inicio and estado.fecha_fin
        ):
            # Alojamiento y vuelos (RapidAPI) necesitan fechas de calendario
            # reales para buscar disponibilidad, a diferencia del plan
            # (armar_plan), que puede armarse solo con duracion_dias.
            pendientes.append({"tipo": "pedir_fechas_exactas"})
            continue
        if tipo == "buscar_vuelos" and not estado.origen:
            pendientes.append({"tipo": "pedir_origen_vuelo"})
            continue
        if tipo == "convertir_moneda" and not estado_grafo.get("ultimo_plan"):
            pendientes.append({"tipo": "pedir_plan_para_convertir"})
            continue
        pendientes.append(accion)

    ultimo_plan = estado_grafo.get("ultimo_plan")
    plan_ya_pendiente = any(p["tipo"] == "armar_plan" for p in pendientes)
    if (
        ultimo_plan
        and not faltantes
        and not plan_ya_pendiente
        and detectar_cambios(estado_anterior, estado)
    ):
        pendientes.append({"tipo": "armar_plan"})

    return {"pendientes": pendientes[:MAXIMO_FRAGMENTOS_POR_TURNO]}


def _resumen_plan(plan: PlanDeViaje) -> str:
    lineas = [f"Armé un plan de {len(plan.dias)} día(s) para **{plan.destino}**:"]
    for dia in plan.dias:
        nombres = ", ".join(a.nombre or "actividad sin nombre" for a in dia.actividades)
        etiqueta = f"Día {dia.dia}" + (f" ({dia.fecha.strftime('%d/%m')})" if dia.fecha else "")
        lineas.append(f"- **{etiqueta}**: {nombres} (costo estimado ${dia.costo_dia:.0f})")
    lineas.append(
        f"\nCosto total estimado: {plan.moneda} {plan.costo_total_estimado:.0f} por persona, "
        f"{plan.moneda} {plan.costo_total_grupo:.0f} para el grupo de {plan.cantidad_personas}."
    )
    if plan.supuestos:
        lineas.append("(" + "; ".join(plan.supuestos) + ")")
    return "\n".join(lineas)


def _resumen_actividades(actividades: list[ActividadRecomendada]) -> str:
    if not actividades:
        return "No encontré actividades para recomendarle con esos intereses en este destino."
    return "\n".join(f"- **{a.nombre}**: {a.justificacion}" for a in actividades)


def _resumen_locales(locales: list[LocalRecomendado]) -> str:
    if not locales:
        return "No encontré locales para recomendarle con esa consulta en este destino."
    return "\n".join(f"- **{local.nombre}**: {local.justificacion}" for local in locales)


def _marca_fixture(es_fixture: bool) -> str:
    # RF6/RF7: si la API real falla, la tool sirve datos de ejemplo
    # (es_fixture=True) para no dejar al cliente sin nada, pero nunca se
    # le puede afirmar que son precios reales (regla dura 5).
    return " (dato de ejemplo, no una tarifa real vigente)" if es_fixture else ""


def _resumen_alojamiento(alojamientos: list[Alojamiento]) -> str:
    if not alojamientos:
        return "No encontré opciones de alojamiento para esas fechas."
    lineas = ["Opciones de alojamiento:"]
    for alojamiento in alojamientos[:3]:
        lineas.append(
            f"- **{alojamiento.nombre}**: {alojamiento.precio_total:.0f} {alojamiento.moneda}"
            f"{_marca_fixture(alojamiento.es_fixture)}"
        )
    return "\n".join(lineas)


def _resumen_vuelos(vuelos: list[OpcionVuelo]) -> str:
    if not vuelos:
        return "No encontré opciones de vuelo para ese origen y esas fechas."
    lineas = ["Opciones de vuelo:"]
    for vuelo in vuelos[:3]:
        aerolineas = ", ".join(vuelo.aerolineas) or "aerolínea sin especificar"
        lineas.append(
            f"- **{aerolineas}**: {vuelo.precio_total:.0f} {vuelo.moneda}, "
            f"{vuelo.escalas or 0} escala(s){_marca_fixture(vuelo.es_fixture)}"
        )
    return "\n".join(lineas)


def nodo_ejecutar_acciones(estado_grafo: EstadoGrafo) -> dict:
    runtime = get_runtime(ContextoGrafo)
    conexion = runtime.context.conexion
    rotador = runtime.context.rotador
    estado = PreferenciasViaje(**estado_grafo["estado"])
    mensaje = estado_grafo["mensaje"]

    fragmentos: list[Fragmento] = []
    ultimo_plan = estado_grafo.get("ultimo_plan")

    for accion in estado_grafo["pendientes"]:
        tipo = accion["tipo"]
        k = accion.get("cantidad_resultados") or CANTIDAD_RESULTADOS_DEFECTO
        consulta = accion.get("consulta") or mensaje
        try:
            if tipo == "destino_no_soportado":
                nombre = estado_grafo.get("destino_no_soportado") or "ese destino"
                texto = f'Por ahora no tengo datos de "{nombre}". ' + destinos_piloto_destacados()
                fragmentos.append({"tipo": tipo, "texto": texto})
            elif tipo == "pedir_datos":
                fragmentos.append(
                    {"tipo": tipo, "texto": armar_pregunta_consolidada(estado.slots_faltantes())}
                )
            elif tipo == "armar_plan":
                plan = armar_plan(conexion, estado)
                guardar_itinerario(conexion, estado, plan)
                fragmentos.append({"tipo": tipo, "texto": _resumen_plan(plan)})
                ultimo_plan = plan.model_dump(mode="json")
            elif tipo == "recomendar_actividades":
                actividades = recomendar_actividades(
                    conexion, rotador, estado.destino, estado.intereses or [], k=k
                )
                fragmentos.append({"tipo": tipo, "texto": _resumen_actividades(actividades)})
            elif tipo == "recomendar_locales":
                locales = recomendar_locales(conexion, rotador, estado.destino, consulta, k=k)
                fragmentos.append({"tipo": tipo, "texto": _resumen_locales(locales)})
            elif tipo == "responder_faq_viajero":
                respuesta = responder_faq_viajero(conexion, rotador, estado.destino, consulta, k=k)
                fragmentos.append({"tipo": tipo, "texto": respuesta.respuesta})
            elif tipo == "pedir_fechas_exactas":
                fragmentos.append(
                    {
                        "tipo": tipo,
                        "texto": "Para buscar alojamiento o vuelos necesito fechas exactas de ida y vuelta, no solo la cantidad de días. ¿Me las confirma?",
                    }
                )
            elif tipo == "pedir_origen_vuelo":
                fragmentos.append({"tipo": tipo, "texto": "¿Desde qué ciudad sale el vuelo?"})
            elif tipo == "pedir_plan_para_convertir":
                fragmentos.append(
                    {
                        "tipo": tipo,
                        "texto": "Todavía no armé un plan con un costo para convertir. ¿Quiere que lo arme primero?",
                    }
                )
            elif tipo == "convertir_moneda":
                monto = (ultimo_plan or {}).get("costo_total_grupo", 0.0)
                moneda_destino = accion.get("moneda_destino") or MONEDA_DESTINO_DEFECTO
                cotizacion = convertir_desde_usd(monto, moneda_destino)
                fragmentos.append({"tipo": tipo, "texto": cotizacion.detalle})
            elif tipo == "buscar_alojamiento":
                habitaciones = -(-(estado.cantidad_personas or 1) // 2)  # ceil(personas/2)
                alojamientos = buscar_alojamiento(
                    conexion,
                    estado.destino,
                    estado.fecha_inicio,
                    estado.fecha_fin,
                    adultos=estado.cantidad_personas or 1,
                    habitaciones=habitaciones,
                )
                fragmentos.append({"tipo": tipo, "texto": _resumen_alojamiento(alojamientos)})
            elif tipo == "buscar_vuelos":
                vuelos = buscar_vuelos(
                    conexion,
                    estado.origen,
                    estado.destino,
                    estado.fecha_inicio,
                    estado.fecha_fin,
                    adultos=estado.cantidad_personas or 1,
                )
                fragmentos.append({"tipo": tipo, "texto": _resumen_vuelos(vuelos)})
        except ErrorFechasIncompletas:
            fragmentos.append(
                {
                    "tipo": tipo,
                    "texto": "Para armar el plan necesito fechas exactas o la cantidad de días del viaje.",
                }
            )
        except Exception:
            logger.exception("fallo la accion '%s', se sigue con las demas del turno", tipo)
            fragmentos.append(
                {
                    "tipo": tipo,
                    "texto": "Tuve un problema puntual con esa parte, pero sigamos con el resto.",
                }
            )

    return {"fragmentos": fragmentos, "ultimo_plan": ultimo_plan}


def nodo_disparar_info_destino(estado_grafo: EstadoGrafo) -> dict:
    """RF12, unica excepcion a que decida el LLM: se dispara sola la
    primera vez que el destino queda confirmado con fecha de inicio, y de
    nuevo si el destino cambia a mitad de conversacion (antes quedaba
    marcada como disparada para siempre en toda la sesion, sin importar
    si el destino cambiaba)."""
    estado = PreferenciasViaje(**estado_grafo["estado"])
    if not (estado.destino and estado.fecha_inicio):
        return {}
    if estado_grafo.get("info_destino_mostrada_para") == estado.destino:
        return {}

    encontrado = buscar_destino_piloto(estado.destino)
    if encontrado is None:
        return {"info_destino_mostrada_para": estado.destino}

    _, datos = encontrado
    try:
        info = info_destino(
            destino=estado.destino,
            pais=datos["pais"],
            lat=datos["lat"],
            lon=datos["lon"],
            fecha_inicio=estado.fecha_inicio,
            fecha_fin=estado.fecha_fin or estado.fecha_inicio,
        )
    except Exception:
        logger.exception("fallo info_destino, se omite en este turno")
        return {"info_destino_mostrada_para": estado.destino}

    texto = f"{info.clima.detalle} Idioma: {info.idioma_moneda.idioma}, moneda: {info.idioma_moneda.moneda}."
    fragmentos = [*estado_grafo["fragmentos"], {"tipo": "info_destino", "texto": texto}]
    return {"fragmentos": fragmentos, "info_destino_mostrada_para": estado.destino}


def nodo_redactar(estado_grafo: EstadoGrafo) -> dict:
    fragmentos = [f for f in estado_grafo["fragmentos"] if f["texto"]]
    if fragmentos:
        return {"respuesta_texto": "\n\n".join(f["texto"] for f in fragmentos)}

    runtime = get_runtime(ContextoGrafo)
    estado = PreferenciasViaje(**estado_grafo["estado"])
    prompt = PROMPT_CONVERSAR.format(
        estado_actual=estado.model_dump(),
        ultimo_plan=estado_grafo.get("ultimo_plan") or "(todavía no hay plan armado)",
        historial=_historial_como_texto(estado_grafo["historial"]),
        mensaje=estado_grafo["mensaje"],
    )
    try:
        respuesta = runtime.context.rotador.invocar(prompt)
        texto = contenido_texto(respuesta)
    except Exception:
        logger.exception("fallo redactar, se usa una respuesta de reserva")
        texto = "Estoy para ayudarlo a planear su viaje. ¿En qué le puedo dar una mano?"
    return {"respuesta_texto": texto}


def construir_grafo():
    """Arma y compila el grafo. Sin checkpointer: la persistencia entre
    turnos es responsabilidad de SesionAgente/conversaciones.py (Fase 7C),
    no del grafo en si (cada invoke() es un turno aislado)."""
    grafo = StateGraph(EstadoGrafo, context_schema=ContextoGrafo)
    grafo.add_node("interpretar", nodo_interpretar)
    grafo.add_node("actualizar_estado", nodo_actualizar_estado)
    grafo.add_node("planificar", nodo_planificar)
    grafo.add_node("ejecutar_acciones", nodo_ejecutar_acciones)
    grafo.add_node("disparar_info_destino", nodo_disparar_info_destino)
    grafo.add_node("redactar", nodo_redactar)

    grafo.add_edge(START, "interpretar")
    grafo.add_edge("interpretar", "actualizar_estado")
    grafo.add_edge("actualizar_estado", "planificar")
    grafo.add_edge("planificar", "ejecutar_acciones")
    grafo.add_edge("ejecutar_acciones", "disparar_info_destino")
    grafo.add_edge("disparar_info_destino", "redactar")
    grafo.add_edge("redactar", END)

    return grafo.compile()


_grafo_compilado = None


def grafo_compilado():
    """Compila el grafo una sola vez por proceso (StateGraph.compile() no
    es gratis y el grafo no cambia entre turnos)."""
    global _grafo_compilado
    if _grafo_compilado is None:
        _grafo_compilado = construir_grafo()
    return _grafo_compilado


def procesar_turno(
    conexion: psycopg.Connection,
    rotador: RotadorClavesGemini,
    mensaje: str,
    historial: list[dict],
    estado: dict,
    ultimo_plan: dict | None,
    info_destino_mostrada_para: str | None,
    hoy: date | None = None,
) -> EstadoGrafo:
    """Punto de entrada del grafo para un turno. agente.py lo envuelve en
    la fachada SesionAgente/procesar_mensaje que usan la UI, el CLI y el
    notebook."""
    contexto = ContextoGrafo(conexion=conexion, rotador=rotador, hoy=hoy or _hoy_argentina())
    entrada: EstadoGrafo = {
        "mensaje": mensaje,
        "historial": historial,
        "estado": estado,
        "estado_anterior": estado,
        "ultimo_plan": ultimo_plan,
        "info_destino_mostrada_para": info_destino_mostrada_para,
        "interpretacion": None,
        "destino_no_soportado": None,
        "acciones_pedidas": [],
        "pendientes": [],
        "fragmentos": [],
        "respuesta_texto": "",
    }
    return grafo_compilado().invoke(entrada, context=contexto, config={"recursion_limit": 15})
