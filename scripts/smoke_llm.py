"""Verifica que la rotacion de claves de Gemini funciona contra la API real.

Unico consumidor de cuota autorizado a correr en CI (workflow manual
smoke-llm.yml). No lo dispares seguido en local, cada clave tiene cuota
diaria limitada.

Uso: python -m scripts.smoke_llm
"""

from __future__ import annotations

import logging
import sys

from asistente_viajes.config import ConfiguracionInvalida, cargar_configuracion
from asistente_viajes.llm import RotadorClavesGemini

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        configuracion = cargar_configuracion()
    except ConfiguracionInvalida as error:
        logger.error(str(error))
        return 1

    cantidad_claves = len(configuracion.claves_gemini)
    logger.info(
        "probando %s clave(s) contra el modelo %s", cantidad_claves, configuracion.gemini_model
    )

    rotador = RotadorClavesGemini(
        claves=configuracion.claves_gemini, modelo=configuracion.gemini_model
    )

    exitos = 0
    for _ in range(cantidad_claves):
        try:
            respuesta = rotador.invocar("Respondé solo con la palabra: ok")
            logger.info("respuesta recibida: %r", getattr(respuesta, "content", respuesta))
            exitos += 1
        except Exception as error:  # noqa: BLE001
            logger.error("fallo la invocacion: %s", error)

    logger.info("%s/%s intentos exitosos", exitos, cantidad_claves)
    return 0 if exitos == cantidad_claves else 1


if __name__ == "__main__":
    sys.exit(main())
