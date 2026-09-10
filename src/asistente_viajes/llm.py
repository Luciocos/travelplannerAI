"""Factory del ChatModel de Gemini con rotador de claves.

Round robin entre las claves disponibles. Ante un 429 marca la clave usada
como no disponible y reintenta con la siguiente, de forma transparente para
quien llama. Distingue limite por minuto (transitorio, 60s) de limite diario
(muerta hasta el reset de Google). Detalle de las reglas en la skill,
references/llm-y-claves.md.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI

from asistente_viajes.config import Configuracion, cargar_configuracion

logger = logging.getLogger(__name__)

SEGUNDOS_BACKOFF_RPM = 60
FALLOS_CONSECUTIVOS_PARA_RPD = 3


@dataclass
class _EstadoClave:
    indice: int
    disponible_desde: float = 0.0
    fallos_consecutivos: int = 0
    agotada_por_hoy: bool = False

    def disponible(self, ahora: float) -> bool:
        return not self.agotada_por_hoy and ahora >= self.disponible_desde


def _es_error_cuota(error: Exception) -> bool:
    texto = str(error).lower()
    return "429" in texto or "quota" in texto or "resource_exhausted" in texto


def _es_limite_diario(error: Exception) -> bool:
    texto = str(error).lower()
    return "per day" in texto or "daily" in texto or "rpd" in texto


class RotadorClavesGemini:
    """Envuelve N claves de Gemini y decide con cual responder cada request."""

    def __init__(self, claves: list[str], modelo: str, **kwargs_modelo: object) -> None:
        if not claves:
            raise ValueError("El rotador necesita al menos una clave.")
        self._claves = claves
        self._modelo = modelo
        self._kwargs_modelo = kwargs_modelo
        self._estados: list[_EstadoClave] = [_EstadoClave(indice=i) for i in range(len(claves))]
        self._siguiente = 0
        self._clientes: dict[int, ChatGoogleGenerativeAI] = {}

    def _cliente(self, indice: int) -> ChatGoogleGenerativeAI:
        if indice not in self._clientes:
            self._clientes[indice] = ChatGoogleGenerativeAI(
                model=self._modelo,
                google_api_key=self._claves[indice],
                **self._kwargs_modelo,
            )
        return self._clientes[indice]

    def _elegir_clave(self) -> int | None:
        ahora = time.monotonic()
        n = len(self._estados)
        for paso in range(n):
            indice = (self._siguiente + paso) % n
            if self._estados[indice].disponible(ahora):
                self._siguiente = (indice + 1) % n
                return indice
        return None

    def _marcar_fallo(self, indice: int, error: Exception) -> None:
        estado = self._estados[indice]
        estado.fallos_consecutivos += 1

        if _es_limite_diario(error) or estado.fallos_consecutivos >= FALLOS_CONSECUTIVOS_PARA_RPD:
            estado.agotada_por_hoy = True
            logger.warning("clave_%s agotada por hoy (limite diario)", indice + 1)
        else:
            estado.disponible_desde = time.monotonic() + SEGUNDOS_BACKOFF_RPM
            logger.warning(
                "clave_%s en backoff por %ss (limite por minuto)",
                indice + 1,
                SEGUNDOS_BACKOFF_RPM,
            )

    def _marcar_exito(self, indice: int) -> None:
        self._estados[indice].fallos_consecutivos = 0

    def _tiempo_espera_minimo(self) -> float:
        ahora = time.monotonic()
        pendientes = [e.disponible_desde - ahora for e in self._estados if not e.agotada_por_hoy]
        return max(0.0, min(pendientes)) if pendientes else 0.0

    def invocar(self, mensajes: object, **kwargs: object) -> object:
        """Invoca el LLM rotando claves. Reintenta una vez tras esperar el
        backoff mas corto si las tres claves estan agotadas."""
        errores: list[Exception] = []

        for _intento_extra in range(2):
            while True:
                indice = self._elegir_clave()
                if indice is None:
                    break
                logger.info("usando clave_%s", indice + 1)
                try:
                    resultado = self._cliente(indice).invoke(mensajes, **kwargs)
                    self._marcar_exito(indice)
                    return resultado
                except Exception as error:
                    if not _es_error_cuota(error):
                        raise
                    self._marcar_fallo(indice, error)
                    errores.append(error)

            espera = self._tiempo_espera_minimo()
            if espera <= 0:
                break
            logger.warning("las claves disponibles estan agotadas, esperando %.0fs", espera)
            time.sleep(espera)

        agotadas = sum(1 for e in self._estados if e.agotada_por_hoy)
        raise RuntimeError(
            f"Las {len(self._claves)} claves de Gemini estan agotadas "
            f"({agotadas} por limite diario). Ultimo error: {errores[-1] if errores else 'desconocido'}"
        )


def crear_rotador(configuracion: Configuracion | None = None) -> RotadorClavesGemini:
    """Factory principal. Usa la configuracion cargada de .env si no se pasa una."""
    configuracion = configuracion or cargar_configuracion()
    if configuracion.llm_provider != "gemini":
        raise ValueError(f"Proveedor no soportado: {configuracion.llm_provider}")
    return RotadorClavesGemini(
        claves=configuracion.claves_gemini, modelo=configuracion.gemini_model
    )
