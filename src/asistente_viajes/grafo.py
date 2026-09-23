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
  solo con la pregunta) — pero solo si algo cambio o el cliente pidio
  algo este turno; si ya se hizo exactamente esa misma pregunta el turno
  anterior y el cliente no aporto nada nuevo (un agradecimiento, un
  comentario), no se repite, y el turno cae en redactar/conversar (bug
  real, P-13: "gracias" quedaba tapado por la misma pregunta de siempre).
  Si el plan ya armado quedo desactualizado por un cambio de dato (ver
  estado.detectar_cambios), se re-arma solo; las acciones que pidio el
  cliente se agregan si sus precondiciones estan cubiertas.
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
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

import psycopg
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from asistente_viajes.ajustes import AjustePlan
from asistente_viajes.destinos import blurb_caracteristicas_destinos, buscar_destino_piloto
from asistente_viajes.destinos_bajo_demanda import DestinoResuelto, asegurar_destino
from asistente_viajes.estado import (
    PreferenciasViaje,
    Tramo,
    detectar_cambios,
    fusionar_preferencias,
    normalizar_presupuesto,
    validar_preferencias,
)
from asistente_viajes.herramientas import construir_herramientas
from asistente_viajes.llm import RotadorClavesGemini, contenido_texto
from asistente_viajes.preguntas import (
    armar_pregunta_consolidada,
    destinos_piloto_destacados,
    tipo_destino_de,
    valores_sugeridos,
)
from asistente_viajes.presentacion import escapar, tarjeta, tarjeta_detallada
from asistente_viajes.prompts import (
    PROMPT_AGENTE,
    PROMPT_INTERPRETAR_TURNO,
    PROMPT_REDACTAR,
)
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
    # Fase 7E (D-22): restricciones sobre como armar el plan. None (no una
    # lista vacia) significa "este turno no hablo de ajustes": ver el
    # comentario de PreferenciasViaje.ajustes, de esa distincion depende
    # que el merge no borre los ajustes vigentes en cada turno.
    ajustes: list[AjustePlan] | None = None
    # Fase 7E (D-24): viajes de varias ciudades. Misma convencion de
    # None vs [] que `ajustes`.
    tramos: list[Tramo] | None = None


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
    """Resultado de una accion del turno, en dos formas que cumplen roles
    distintos desde la Fase 7E (D-22):

    - `texto`: la tarjeta HTML que ve el cliente, armada en Python a partir
      de datos reales. Vacia si esta accion no tiene nada que tabular.
    - `datos`: los mismos hechos en texto plano, que se le pasan al LLM
      para que redacte el mensaje del turno (PROMPT_REDACTAR).

    La separacion es deliberada: la prosa la escribe el modelo (que es lo
    que saca la rigidez), pero ningun numero ni nombre sale de el, salen de
    la tarjeta. Asi se gana flexibilidad de redaccion sin poder inventar un
    precio o un lugar.
    """

    tipo: str
    texto: str
    datos: str


class EstadoGrafo(TypedDict):
    mensaje: str
    historial: list[dict]
    estado: dict
    estado_anterior: dict
    ultimo_plan: dict | None
    info_destino_mostrada_para: str | None
    pedir_datos_mostrado_para: list[str] | None
    interpretacion: dict | None
    destino_no_soportado: str | None
    destino_recien_ingerido: str | None
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


def _resolver_destino(conexion: psycopg.Connection, destino: str) -> DestinoResuelto | None:
    """asegurar_destino() blindado: la ingesta bajo demanda toca la red y
    el modelo de embeddings, y ninguno de los dos puede voltear un turno.
    Ante cualquier error se sigue con el destino tal como lo dijo el
    cliente (si ya tenia corpus, las consultas van a funcionar igual)."""
    try:
        return asegurar_destino(conexion, destino)
    except Exception:
        logger.exception("fallo resolver el destino '%s', se sigue sin ingerirlo", destino)
        return DestinoResuelto(nombre=destino, lat=0.0, lon=0.0)


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
        ajustes=interpretacion.ajustes,
        tramos=interpretacion.tramos,
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

    # D-23: cualquier ciudad es un destino valido. Si todavia no tiene
    # corpus, se ingiere en este mismo turno y queda cargada para siempre;
    # solo si el geocoder no la reconoce se la trata como no soportada.
    # D-24: `destino` sigue apuntando al primer tramo, que es lo que usan
    # las tools de una sola ciudad (info_destino, alojamiento, vuelos).
    if fusionado.tramos and fusionado.tramos[0].destino != fusionado.destino:
        fusionado = fusionado.model_copy(update={"destino": fusionado.tramos[0].destino})

    destino_no_soportado = interpretacion.destino_fuera_de_alcance
    destino_recien_ingerido = None
    for tramo in fusionado.tramos_activos()[1:]:
        # Cada ciudad del viaje tiene que quedar cargada en pgvector, no
        # solo la primera, o el tramo se arma sin atractivos.
        _resolver_destino(runtime.context.conexion, tramo.destino)

    if fusionado.destino:
        resuelto = _resolver_destino(runtime.context.conexion, fusionado.destino)
        if resuelto is None:
            destino_no_soportado = fusionado.destino
            fusionado = fusionado.model_copy(update={"destino": None, "tipo_destino": None})
        else:
            if resuelto.nombre != fusionado.destino:
                fusionado = fusionado.model_copy(update={"destino": resuelto.nombre})
            if resuelto.recien_ingerido:
                destino_recien_ingerido = resuelto.nombre

    return {
        "estado": fusionado.model_dump(mode="json"),
        "estado_anterior": estado_grafo["estado"],
        "destino_no_soportado": destino_no_soportado if fusionado.destino is None else None,
        "destino_recien_ingerido": destino_recien_ingerido,
        "acciones_pedidas": [accion.model_dump() for accion in interpretacion.acciones],
    }


def nodo_planificar(estado_grafo: EstadoGrafo) -> dict:
    estado = PreferenciasViaje(**estado_grafo["estado"])
    estado_anterior = PreferenciasViaje(**estado_grafo["estado_anterior"])
    faltantes = estado.slots_faltantes()
    faltantes_ordenados = sorted(faltantes)
    pendientes: list[dict] = []

    if estado_grafo.get("destino_no_soportado"):
        pendientes.append({"tipo": "destino_no_soportado"})

    pedir_datos_mostrado_para = estado_grafo.get("pedir_datos_mostrado_para")
    if faltantes:
        # P-13: si ya se hizo exactamente esta misma pregunta el turno
        # anterior, y el cliente no aporto ningun dato nuevo ni pidio
        # ninguna accion, no se repite (tapaba respuestas a "gracias" o
        # comentarios sueltos con la misma pregunta de siempre). Un
        # cambio de estado o un pedido explicito si la vuelve a disparar.
        ya_se_pregunto_lo_mismo = pedir_datos_mostrado_para == faltantes_ordenados
        hubo_cambio = detectar_cambios(estado_anterior, estado)
        hay_pedido_explicito = bool(estado_grafo["acciones_pedidas"])
        if not ya_se_pregunto_lo_mismo or hubo_cambio or hay_pedido_explicito:
            pendientes.append({"tipo": "pedir_datos"})
            if estado.destino:
                # Nunca se deja al cliente solo con la pregunta: si ya hay
                # destino, se suma algo util en el mismo turno.
                pendientes.append({"tipo": "recomendar_actividades", "cantidad_resultados": 3})
            pedir_datos_mostrado_para = faltantes_ordenados
    else:
        pedir_datos_mostrado_para = None

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

    return {
        "pendientes": pendientes[:MAXIMO_FRAGMENTOS_POR_TURNO],
        "pedir_datos_mostrado_para": pedir_datos_mostrado_para,
    }


def _resumen_plan(plan: PlanDeViaje) -> str:
    """La tarjeta del itinerario. Ya no lleva frase de presentación: esa la
    escribe el LLM arriba de la tarjeta (D-22), aca van solo los datos."""
    filas: list[dict[str, str | None]] = []
    for dia in plan.dias:
        etiqueta = f"Día {dia.dia}"
        ciudades = {d.destino for d in plan.dias if d.destino}
        if len(ciudades) > 1 and dia.destino:
            etiqueta += f"<br><span style='opacity:0.7'>{escapar(dia.destino)}</span>"
        if dia.fecha:
            etiqueta += f"<br><span style='opacity:0.6'>{dia.fecha.strftime('%d/%m')}</span>"
        filas.append(
            {
                "etiqueta": etiqueta,
                "cuerpo": escapar(
                    ", ".join(a.nombre or "actividad sin nombre" for a in dia.actividades)
                ),
                "monto": f"${dia.costo_dia:.0f}",
            }
        )

    total = (
        f"<strong>Total estimado: {escapar(plan.moneda)} {plan.costo_total_estimado:.0f} "
        f"por persona</strong> · {escapar(plan.moneda)} {plan.costo_total_grupo:.0f} "
        f"para {plan.cantidad_personas} persona(s)"
    )
    if plan.supuestos:
        total += f"<br>{escapar('; '.join(plan.supuestos))}"

    return tarjeta_detallada(f"Itinerario · {escapar(plan.destino)}", filas, total)


def _resumen_actividades(actividades: list[ActividadRecomendada]) -> str:
    if not actividades:
        return "No encontré actividades para recomendarle con esos intereses en este destino."
    filas = [
        f"<strong>{escapar(a.nombre)}</strong>: {escapar(a.justificacion)}" for a in actividades
    ]
    return tarjeta("Actividades recomendadas", filas)


def _resumen_locales(locales: list[LocalRecomendado]) -> str:
    if not locales:
        return "No encontré locales para recomendarle con esa consulta en este destino."
    filas = [
        f"<strong>{escapar(local.nombre)}</strong>: {escapar(local.justificacion)}"
        for local in locales
    ]
    return tarjeta("Locales recomendados", filas)


def _marca_fixture(es_fixture: bool) -> str:
    # RF6/RF7: si la API real falla, la tool sirve datos de ejemplo
    # (es_fixture=True) para no dejar al cliente sin nada, pero nunca se
    # le puede afirmar que son precios reales (regla dura 5).
    return " (dato de ejemplo, no una tarifa real vigente)" if es_fixture else ""


def _resumen_alojamiento(alojamientos: list[Alojamiento]) -> str:
    if not alojamientos:
        return "No encontré opciones de alojamiento para esas fechas."
    filas: list[dict[str, str | None]] = [
        {
            "cuerpo": escapar(alojamiento.nombre)
            + escapar(_marca_fixture(alojamiento.es_fixture)),
            "monto": f"{alojamiento.precio_total:.0f} {escapar(alojamiento.moneda)}",
        }
        for alojamiento in alojamientos[:3]
    ]
    return tarjeta_detallada("Opciones de alojamiento", filas)


def _resumen_vuelos(vuelos: list[OpcionVuelo]) -> str:
    if not vuelos:
        return "No encontré opciones de vuelo para ese origen y esas fechas."
    filas = []
    for vuelo in vuelos[:3]:
        aerolineas = escapar(", ".join(vuelo.aerolineas) or "aerolínea sin especificar")
        filas.append(
            f"<strong>{aerolineas}</strong>: {vuelo.precio_total:.0f} {escapar(vuelo.moneda)}, "
            f"{vuelo.escalas or 0} escala(s){escapar(_marca_fixture(vuelo.es_fixture))}"
        )
    return tarjeta("Opciones de vuelo", filas)


def _fragmento(tipo: str, texto: str = "", datos: str = "") -> Fragmento:
    """Un fragmento con sus dos caras (ver Fragmento). `texto` vacio es lo
    normal en las acciones que no tienen nada que tabular: esas viven solo
    como datos para que el LLM las exprese con sus palabras."""
    return {"tipo": tipo, "texto": texto, "datos": datos}


def _datos_plan(plan: PlanDeViaje) -> str:
    """El plan en texto plano para el redactor. Incluye el detalle completo
    aunque la tarjeta ya lo muestre: el modelo necesita ver los nombres
    para poder destacar alguno, y asi no tiene que inventarlo."""
    lineas = [f"Plan de {len(plan.dias)} dia(s) para {plan.destino}:"]
    for dia in plan.dias:
        nombres = ", ".join(a.nombre or "actividad sin nombre" for a in dia.actividades)
        fecha = f" ({dia.fecha.strftime('%d/%m')})" if dia.fecha else ""
        lineas.append(f"  Dia {dia.dia}{fecha}: {nombres} (USD {dia.costo_dia:.0f})")
    lineas.append(
        f"Costo total: USD {plan.costo_total_estimado:.0f} por persona, "
        f"USD {plan.costo_total_grupo:.0f} para {plan.cantidad_personas} persona(s)."
    )
    if plan.supuestos:
        lineas.append("Supuestos: " + "; ".join(plan.supuestos) + ".")
    return "\n".join(lineas)


def _datos_recomendaciones(
    clase: str, recomendaciones: list[ActividadRecomendada] | list[LocalRecomendado]
) -> str:
    if not recomendaciones:
        return f"No se encontraron {clase} para esa consulta en este destino."
    lineas = [f"Se recuperaron estas {clase} del corpus:"]
    lineas += [f"  {r.nombre}: {r.justificacion}" for r in recomendaciones]
    return "\n".join(lineas)


def _datos_alojamiento(alojamientos: list[Alojamiento]) -> str:
    if not alojamientos:
        return "No se encontraron opciones de alojamiento para esas fechas."
    lineas = ["Opciones de alojamiento encontradas:"]
    for alojamiento in alojamientos[:3]:
        lineas.append(
            f"  {alojamiento.nombre}: {alojamiento.precio_total:.0f} {alojamiento.moneda}"
            f"{_marca_fixture(alojamiento.es_fixture)}"
        )
    return "\n".join(lineas)


def _datos_vuelos(vuelos: list[OpcionVuelo]) -> str:
    if not vuelos:
        return "No se encontraron opciones de vuelo para ese origen y esas fechas."
    lineas = ["Opciones de vuelo encontradas:"]
    for vuelo in vuelos[:3]:
        aerolineas = ", ".join(vuelo.aerolineas) or "aerolinea sin especificar"
        lineas.append(
            f"  {aerolineas}: {vuelo.precio_total:.0f} {vuelo.moneda}, "
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
                fragmentos.append(
                    _fragmento(
                        tipo,
                        datos=(
                            f'El cliente nombro "{nombre}", que no es un destino disponible. '
                            + destinos_piloto_destacados()
                        ),
                    )
                )
            elif tipo == "pedir_datos":
                # Ya no se arma la pregunta en Python (D-14): los faltantes
                # van al prompt de redaccion y la pregunta la escribe el
                # LLM con sus palabras. armar_pregunta_consolidada queda
                # como red de seguridad si la redaccion falla.
                fragmentos.append(_fragmento(tipo))
            elif tipo == "armar_plan":
                plan = armar_plan(conexion, estado)
                guardar_itinerario(conexion, estado, plan)
                fragmentos.append(
                    _fragmento(tipo, texto=_resumen_plan(plan), datos=_datos_plan(plan))
                )
                ultimo_plan = plan.model_dump(mode="json")
            elif tipo == "recomendar_actividades":
                actividades = recomendar_actividades(
                    conexion, rotador, estado.destino, estado.intereses or [], k=k
                )
                fragmentos.append(
                    _fragmento(
                        tipo,
                        texto=_resumen_actividades(actividades),
                        datos=_datos_recomendaciones("actividades", actividades),
                    )
                )
            elif tipo == "recomendar_locales":
                locales = recomendar_locales(conexion, rotador, estado.destino, consulta, k=k)
                fragmentos.append(
                    _fragmento(
                        tipo,
                        texto=_resumen_locales(locales),
                        datos=_datos_recomendaciones("locales", locales),
                    )
                )
            elif tipo == "responder_faq_viajero":
                respuesta = responder_faq_viajero(conexion, rotador, estado.destino, consulta, k=k)
                fragmentos.append(_fragmento(tipo, datos=respuesta.respuesta))
            elif tipo == "pedir_fechas_exactas":
                fragmentos.append(
                    _fragmento(
                        tipo,
                        datos=(
                            "Para buscar alojamiento o vuelos hacen falta fechas exactas de ida "
                            "y vuelta, no alcanza con la cantidad de dias. Hay que pedirselas."
                        ),
                    )
                )
            elif tipo == "pedir_origen_vuelo":
                fragmentos.append(
                    _fragmento(
                        tipo, datos="Falta saber desde que ciudad sale el vuelo. Hay que preguntarlo."
                    )
                )
            elif tipo == "pedir_plan_para_convertir":
                fragmentos.append(
                    _fragmento(
                        tipo,
                        datos=(
                            "Todavia no hay un plan armado con un costo para convertir. "
                            "Se le puede ofrecer armarlo primero."
                        ),
                    )
                )
            elif tipo == "convertir_moneda":
                monto = (ultimo_plan or {}).get("costo_total_grupo", 0.0)
                moneda_destino = accion.get("moneda_destino") or MONEDA_DESTINO_DEFECTO
                cotizacion = convertir_desde_usd(monto, moneda_destino)
                fragmentos.append(_fragmento(tipo, datos=cotizacion.detalle))
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
                fragmentos.append(
                    _fragmento(
                        tipo,
                        texto=_resumen_alojamiento(alojamientos),
                        datos=_datos_alojamiento(alojamientos),
                    )
                )
            elif tipo == "buscar_vuelos":
                vuelos = buscar_vuelos(
                    conexion,
                    estado.origen,
                    estado.destino,
                    estado.fecha_inicio,
                    estado.fecha_fin,
                    adultos=estado.cantidad_personas or 1,
                )
                fragmentos.append(
                    _fragmento(tipo, texto=_resumen_vuelos(vuelos), datos=_datos_vuelos(vuelos))
                )
        except ErrorFechasIncompletas:
            fragmentos.append(
                _fragmento(
                    tipo,
                    datos=(
                        "No se pudo armar el plan: faltan las fechas exactas o la cantidad de "
                        "dias del viaje. Hay que pedirselas."
                    ),
                )
            )
        except Exception:
            logger.exception("fallo la accion '%s', se sigue con las demas del turno", tipo)
            fragmentos.append(
                _fragmento(
                    tipo,
                    datos=(
                        f"Hubo un problema tecnico puntual ejecutando '{tipo}'. Hay que "
                        "avisarselo con naturalidad y seguir con el resto del turno."
                    ),
                )
            )

    return {"fragmentos": fragmentos, "ultimo_plan": ultimo_plan}


MAXIMO_VUELTAS_DE_HERRAMIENTAS = 4


def _agente_de_herramientas_activo() -> bool:
    """D-25: el agente de tool calling convive con el orquestador de
    precondiciones detras de un flag, en vez de reemplazarlo de una. Es un
    cambio de fondo en como se decide que hacer cada turno, y el camino
    viejo ya estaba verificado; hasta que el nuevo acumule uso real, el
    default sigue siendo el conocido."""
    return os.environ.get("AGENTE_TOOL_CALLING", "").strip().lower() in ("1", "true", "si")


def nodo_agente_herramientas(estado_grafo: EstadoGrafo) -> dict:
    """El LLM ve el catalogo de tools y decide solo cuales llamar, pudiendo
    encadenar varias, en vez de que lo decida `nodo_planificar` con ifs.

    Las tools ejecutan y devuelven hechos; la redaccion sigue siendo la de
    siempre (D-22), asi que ningun dato duro sale del modelo. Si algo falla,
    el turno cae al camino de precondiciones en vez de quedarse sin
    respuesta."""
    runtime = get_runtime(ContextoGrafo)
    estado = PreferenciasViaje(**estado_grafo["estado"])

    herramientas, acumulador = construir_herramientas(
        conexion=runtime.context.conexion,
        rotador=runtime.context.rotador,
        estado=estado,
        hoy=runtime.context.hoy,
        ultimo_plan=estado_grafo.get("ultimo_plan"),
    )
    por_nombre = {herramienta.name: herramienta for herramienta in herramientas}

    mensajes: list = [
        SystemMessage(
            content=PROMPT_AGENTE.format(
                fecha_hoy=runtime.context.hoy.isoformat(),
                estado_actual=estado.model_dump(mode="json"),
                faltantes=", ".join(estado.slots_faltantes()) or "(ninguno)",
                hay_plan="sí" if estado_grafo.get("ultimo_plan") else "no",
            )
        ),
        *[
            (HumanMessage(content=t["texto"]) if t["rol"] == "usuario" else AIMessage(content=t["texto"]))
            for t in estado_grafo["historial"][-TURNOS_DE_HISTORIAL:]
        ],
        HumanMessage(content=estado_grafo["mensaje"]),
    ]

    modelo = runtime.context.rotador.con_herramientas(herramientas)
    for _vuelta in range(MAXIMO_VUELTAS_DE_HERRAMIENTAS):
        respuesta = modelo.invoke(mensajes)
        llamadas = getattr(respuesta, "tool_calls", None) or []
        if not llamadas:
            break

        mensajes.append(respuesta)
        for llamada in llamadas:
            herramienta = por_nombre.get(llamada["name"])
            if herramienta is None:
                salida = f"La herramienta '{llamada['name']}' no existe."
            else:
                try:
                    salida = herramienta.invoke(llamada["args"]).get("datos", "")
                except Exception as error:
                    logger.exception("fallo la tool %s", llamada["name"])
                    salida = f"No se pudo ejecutar: {error}"
            mensajes.append(ToolMessage(content=str(salida), tool_call_id=llamada["id"]))

    return {
        "fragmentos": [*estado_grafo["fragmentos"], *acumulador["fragmentos"]],
        "ultimo_plan": acumulador["ultimo_plan"],
    }


def nodo_disparar_info_destino(estado_grafo: EstadoGrafo) -> dict:
    """RF12, unica excepcion a que decida el LLM: se dispara sola la
    primera vez que el destino queda confirmado con fecha de inicio, y de
    nuevo si el destino cambia a mitad de conversacion (antes quedaba
    marcada como disparada para siempre en toda la sesion, sin importar
    si el destino cambiaba)."""
    runtime = get_runtime(ContextoGrafo)
    estado = PreferenciasViaje(**estado_grafo["estado"])
    if not (estado.destino and estado.fecha_inicio):
        return {}
    if estado_grafo.get("info_destino_mostrada_para") == estado.destino:
        return {}

    # D-23: las coordenadas ya no salen solo de destinos.json. Un destino
    # ingerido bajo demanda tambien tiene lat/lon (de geoname), asi que el
    # clima funciona para cualquier ciudad; idioma y moneda pueden faltar
    # si el pais no esta en paises.json, y en ese caso se omiten en vez de
    # inventarlos.
    encontrado = buscar_destino_piloto(estado.destino)
    if encontrado is not None:
        _, datos = encontrado
        lat, lon, pais = datos["lat"], datos["lon"], datos["pais"]
    else:
        resuelto = _resolver_destino(runtime.context.conexion, estado.destino)
        if resuelto is None or not (resuelto.lat or resuelto.lon):
            return {"info_destino_mostrada_para": estado.destino}
        lat, lon, pais = resuelto.lat, resuelto.lon, resuelto.pais or ""

    try:
        info = info_destino(
            destino=estado.destino,
            pais=pais,
            lat=lat,
            lon=lon,
            fecha_inicio=estado.fecha_inicio,
            fecha_fin=estado.fecha_fin or estado.fecha_inicio,
        )
    except Exception:
        logger.exception("fallo info_destino, se omite en este turno")
        return {"info_destino_mostrada_para": estado.destino}

    filas = [escapar(info.clima.detalle)]
    if info.idioma_moneda.idioma and info.idioma_moneda.moneda:
        filas.append(
            f"Idioma: {escapar(info.idioma_moneda.idioma)}, "
            f"moneda: {escapar(info.idioma_moneda.moneda)}."
        )
    texto = tarjeta(f"Sobre {escapar(estado.destino)}", filas)
    datos_llm = f"Informacion de {estado.destino}: " + " ".join(
        [
            info.clima.detalle,
            (
                f"Idioma: {info.idioma_moneda.idioma}, moneda: {info.idioma_moneda.moneda}."
                if info.idioma_moneda.idioma
                else "No hay dato de idioma ni moneda para este pais."
            ),
        ]
    )
    fragmentos = [
        *estado_grafo["fragmentos"],
        _fragmento("info_destino", texto=texto, datos=datos_llm),
    ]
    return {"fragmentos": fragmentos, "info_destino_mostrada_para": estado.destino}


def _respuesta_de_reserva(estado_grafo: EstadoGrafo, tarjetas: list[str]) -> str:
    """Red de seguridad para cuando la redaccion falla (cuota agotada,
    timeout). Vuelve al comportamiento determinista de la Fase 7D: la
    pregunta armada en Python mas las tarjetas. Feo, pero nunca deja al
    cliente sin respuesta."""
    estado = PreferenciasViaje(**estado_grafo["estado"])
    partes = []
    if any(f["tipo"] == "pedir_datos" for f in estado_grafo["fragmentos"]):
        partes.append(armar_pregunta_consolidada(estado.slots_faltantes()))
    partes.extend(tarjetas)
    if not partes:
        partes.append("Estoy para ayudarlo a planear su viaje. ¿En qué le puedo dar una mano?")
    return "\n\n".join(parte for parte in partes if parte)


def nodo_redactar(estado_grafo: EstadoGrafo) -> dict:
    """UN llamado al LLM redacta el mensaje del turno, siempre (D-22).

    Hasta la Fase 7D esto era al reves: si alguna accion habia producido
    texto, se concatenaban las plantillas de Python y el LLM no escribia
    nada; solo redactaba cuando no habia pasado nada. El resultado era un
    asistente que contestaba siempre igual y no podia acusar recibo de lo
    que el cliente pedia (P-14). Ahora el modelo escribe la prosa de todos
    los turnos, y las tarjetas (armadas en Python con datos reales) se
    adjuntan debajo: la flexibilidad la pone el LLM, los datos duros no
    pasan nunca por el.
    """
    runtime = get_runtime(ContextoGrafo)
    estado = PreferenciasViaje(**estado_grafo["estado"])
    fragmentos = estado_grafo["fragmentos"]
    tarjetas = [f["texto"] for f in fragmentos if f.get("texto")]

    ultimo_plan = estado_grafo.get("ultimo_plan") or {}
    prompt = PROMPT_REDACTAR.format(
        fecha_hoy=runtime.context.hoy.isoformat(),
        estado_actual=estado.model_dump(mode="json"),
        faltantes=", ".join(estado.slots_faltantes()) or "(ninguno)",
        ajustes_aplicados="; ".join(ultimo_plan.get("ajustes_aplicados") or []) or "(ninguno)",
        ajustes_no_aplicados=(
            "; ".join(ultimo_plan.get("ajustes_no_aplicados") or []) or "(ninguno)"
        ),
        resultados="\n\n".join(f["datos"] for f in fragmentos if f.get("datos"))
        or "(no se ejecuto ninguna accion en este turno)",
        historial=_historial_como_texto(estado_grafo["historial"]),
        mensaje=estado_grafo["mensaje"],
    )

    try:
        prosa = contenido_texto(runtime.context.rotador.invocar(prompt))
    except Exception:
        logger.exception("fallo redactar, se usa la respuesta determinista de reserva")
        return {"respuesta_texto": _respuesta_de_reserva(estado_grafo, tarjetas)}

    if not prosa:
        return {"respuesta_texto": _respuesta_de_reserva(estado_grafo, tarjetas)}

    return {"respuesta_texto": "\n\n".join([prosa, *tarjetas])}


def construir_grafo():
    """Arma y compila el grafo. Sin checkpointer: la persistencia entre
    turnos es responsabilidad de SesionAgente/conversaciones.py (Fase 7C),
    no del grafo en si (cada invoke() es un turno aislado)."""
    grafo = StateGraph(EstadoGrafo, context_schema=ContextoGrafo)
    grafo.add_node("interpretar", nodo_interpretar)
    grafo.add_node("actualizar_estado", nodo_actualizar_estado)
    grafo.add_node("planificar", nodo_planificar)
    grafo.add_node("ejecutar_acciones", nodo_ejecutar_acciones)
    grafo.add_node("agente_herramientas", nodo_agente_herramientas)
    grafo.add_node("disparar_info_destino", nodo_disparar_info_destino)
    grafo.add_node("redactar", nodo_redactar)

    grafo.add_edge(START, "interpretar")
    grafo.add_edge("interpretar", "actualizar_estado")
    grafo.add_edge("actualizar_estado", "planificar")
    grafo.add_conditional_edges(
        "planificar",
        lambda _estado: (
            "agente_herramientas" if _agente_de_herramientas_activo() else "ejecutar_acciones"
        ),
        ["agente_herramientas", "ejecutar_acciones"],
    )
    grafo.add_edge("ejecutar_acciones", "disparar_info_destino")
    grafo.add_edge("agente_herramientas", "disparar_info_destino")
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
    pedir_datos_mostrado_para: list[str] | None = None,
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
        "pedir_datos_mostrado_para": pedir_datos_mostrado_para,
        "interpretacion": None,
        "destino_no_soportado": None,
        "destino_recien_ingerido": None,
        "acciones_pedidas": [],
        "pendientes": [],
        "fragmentos": [],
        "respuesta_texto": "",
    }
    return grafo_compilado().invoke(entrada, context=contexto, config={"recursion_limit": 15})
