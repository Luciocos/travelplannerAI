"""Harness de evaluación contra LLM real (Fase 7D, Paso 8 del plan).

Corre los escenarios guionados de `escenarios_conversacion.json`, turno a
turno, contra Gemini y Postgres reales, y verifica que cada respuesta
cumpla lo esperado (contiene / no contiene ciertos textos). Nunca se
corre en CI: consume cuota real de LLM, y ese es justamente el motivo
por el que este harness es un script manual y no una suite de pytest
(regla dura del proyecto: ningún proceso automático consume cuota).

Uso:
    python -m scripts.evaluar_conversaciones
    python -m scripts.evaluar_conversaciones --escenario recap_memoria
    python -m scripts.evaluar_conversaciones --pausa 5
    USE_FIXTURES=true python -m scripts.evaluar_conversaciones
    LLM_CACHE=true python -m scripts.evaluar_conversaciones
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from asistente_viajes.agente import SesionAgente, procesar_mensaje
from asistente_viajes.config import ConfiguracionInvalida
from asistente_viajes.db import obtener_conexion
from asistente_viajes.llm import crear_rotador

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RUTA_ESCENARIOS = Path(__file__).parent / "escenarios_conversacion.json"
RUTA_REPORTES = Path(__file__).parent.parent / "docs" / "evaluacion"

# "Hoy" fijo para que las fechas relativas de los escenarios ("del 5 al
# 10 de marzo de 2027") sean siempre futuras, sin depender de cuando se
# corra el harness (ver validar_preferencias, que rechaza fechas pasadas).
HOY_DE_REFERENCIA = date(2027, 1, 1)


@dataclass
class ResultadoTurno:
    mensaje: str
    respuesta: str
    fallas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fallas


@dataclass
class ResultadoEscenario:
    nombre: str
    turnos: list[ResultadoTurno] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(turno.ok for turno in self.turnos)


def _verificar_turno(respuesta: str, spec: dict) -> list[str]:
    fallas = []
    respuesta_normalizada = respuesta.lower()
    for esperado in spec.get("debe_contener", []):
        if esperado.lower() not in respuesta_normalizada:
            fallas.append(f'esperaba encontrar "{esperado}"')
    for prohibido in spec.get("no_debe_contener", []):
        if prohibido.lower() in respuesta_normalizada:
            fallas.append(f'no debía contener "{prohibido}"')
    return fallas


def ejecutar_escenario(conexion, rotador, escenario: dict, pausa: float) -> ResultadoEscenario:
    sesion = SesionAgente()
    resultado = ResultadoEscenario(nombre=escenario["nombre"])
    for turno_spec in escenario["turnos"]:
        mensaje = turno_spec["mensaje"]
        try:
            respuesta = procesar_mensaje(conexion, rotador, sesion, mensaje, hoy=HOY_DE_REFERENCIA)
        except Exception as error:
            logger.exception("turno del escenario '%s' tiró una excepción", escenario["nombre"])
            resultado.turnos.append(ResultadoTurno(mensaje, "", [f"excepción: {error!r}"]))
            continue
        fallas = _verificar_turno(respuesta, turno_spec)
        resultado.turnos.append(ResultadoTurno(mensaje, respuesta, fallas))
        if pausa:
            time.sleep(pausa)
    return resultado


def _reporte_markdown(resultados: list[ResultadoEscenario]) -> str:
    total_turnos = sum(len(r.turnos) for r in resultados)
    turnos_ok = sum(1 for r in resultados for t in r.turnos if t.ok)
    lineas = [
        "# Reporte de evaluación de conversaciones",
        "",
        f"{turnos_ok}/{total_turnos} turnos OK en {len(resultados)} escenario(s).",
        "",
    ]
    for r in resultados:
        marca_escenario = "✅" if r.ok else "❌"
        lineas.append(f"## {marca_escenario} {r.nombre}")
        for i, t in enumerate(r.turnos, start=1):
            marca_turno = "✅" if t.ok else "❌"
            lineas.append(f"\n**Turno {i}** {marca_turno} — _{t.mensaje}_\n")
            lineas.append(f"> {t.respuesta}")
            if t.fallas:
                lineas.append("\nFallas: " + "; ".join(t.fallas))
        lineas.append("")
    return "\n".join(lineas)


def _activar_cache_llm() -> None:
    from langchain.globals import set_llm_cache
    from langchain_community.cache import SQLiteCache

    Path(".cache").mkdir(exist_ok=True)
    set_llm_cache(SQLiteCache(database_path=".cache/llm_cache.sqlite"))
    logger.info("cache de LLM activado en .cache/llm_cache.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--escenario", help="corre solo el escenario con este nombre")
    parser.add_argument(
        "--pausa", type=float, default=3.0, help="segundos de espera entre turnos (cuota)"
    )
    args = parser.parse_args()

    if os.environ.get("LLM_CACHE", "").lower() == "true":
        _activar_cache_llm()

    escenarios = json.loads(RUTA_ESCENARIOS.read_text(encoding="utf-8"))
    if args.escenario:
        escenarios = [e for e in escenarios if e["nombre"] == args.escenario]
        if not escenarios:
            print(f"no existe un escenario llamado '{args.escenario}'")
            return 1

    try:
        rotador = crear_rotador()
    except ConfiguracionInvalida as error:
        print(f"Error de configuración: {error}")
        return 1

    resultados = []
    with obtener_conexion() as conexion:
        for escenario in escenarios:
            print(f"corriendo escenario: {escenario['nombre']}")
            resultados.append(ejecutar_escenario(conexion, rotador, escenario, args.pausa))

    RUTA_REPORTES.mkdir(parents=True, exist_ok=True)
    hoy = datetime.now(tz=UTC).date().isoformat()
    ruta_reporte = RUTA_REPORTES / f"reporte_{hoy}.md"
    ruta_reporte.write_text(_reporte_markdown(resultados), encoding="utf-8")
    print(f"reporte escrito en {ruta_reporte}")

    total_turnos = sum(len(r.turnos) for r in resultados)
    turnos_ok = sum(1 for r in resultados for t in r.turnos if t.ok)
    print(f"{turnos_ok}/{total_turnos} turnos OK")
    return 0 if turnos_ok == total_turnos else 1


if __name__ == "__main__":
    sys.exit(main())
