"""CLI interactivo para probar el orquestador a mano (RF11/RF12).

Uso: python -m scripts.chat
Escribir 'salir' (o Ctrl+C) para terminar. La sesion (estado del viaje)
vive solo mientras corre este proceso, no se persiste entre corridas.
"""

from __future__ import annotations

import logging
import sys

from asistente_viajes.agente import SesionAgente, procesar_mensaje
from asistente_viajes.config import ConfiguracionInvalida
from asistente_viajes.db import obtener_conexion
from asistente_viajes.llm import crear_rotador

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")


def main() -> int:
    try:
        rotador = crear_rotador()
    except ConfiguracionInvalida as error:
        print(f"Error de configuracion: {error}")
        return 1

    sesion = SesionAgente()
    print("Asistente de viajes (Ctrl+C o 'salir' para terminar)\n")

    try:
        with obtener_conexion() as conexion:
            while True:
                try:
                    mensaje = input("Vos: ").strip()
                except EOFError:
                    break
                if mensaje.lower() in {"salir", "exit", "quit"}:
                    break
                if not mensaje:
                    continue
                respuesta = procesar_mensaje(conexion, rotador, sesion, mensaje)
                print(f"\nAsistente: {respuesta}\n")
    except KeyboardInterrupt:
        print("\nChau!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
