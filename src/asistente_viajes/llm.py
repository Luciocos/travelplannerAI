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
    return (
        "429" in texto
        or "quota" in texto
        or "resource_exhausted" in texto
        or "503" in texto
        or "unavailable" in texto
    )


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

    def _ejecutar_con_rotacion(self, invocar_con_cliente):
        """Nucleo comun de reintentos: prueba cada clave disponible con el
        callable dado (recibe el cliente de una clave), rota ante error de
        cuota, y espera el backoff mas corto si las tres estan agotadas."""
        errores: list[Exception] = []

        for _intento_extra in range(2):
            while True:
                indice = self._elegir_clave()
                if indice is None:
                    break
                logger.info("usando clave_%s", indice + 1)
                try:
                    resultado = invocar_con_cliente(self._cliente(indice))
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

    def invocar(self, mensajes: object, **kwargs: object) -> object:
        """Invoca el LLM rotando claves. Reintenta una vez tras esperar el
        backoff mas corto si las tres claves estan agotadas."""
        return self._ejecutar_con_rotacion(lambda cliente: cliente.invoke(mensajes, **kwargs))

    def con_salida_estructurada(self, esquema: type) -> _SalidaEstructuradaRotada:
        """Equivalente rotado de ChatModel.with_structured_output(esquema).
        Devuelve un objeto con .invoke(mensajes) que aplica la misma logica
        de rotacion y failover que invocar()."""
        return _SalidaEstructuradaRotada(self, esquema)


class _SalidaEstructuradaRotada:
    def __init__(self, rotador: RotadorClavesGemini, esquema: type) -> None:
        self._rotador = rotador
        self._esquema = esquema

    def invoke(self, mensajes: object, **kwargs: object) -> object:
        return self._rotador._ejecutar_con_rotacion(
            lambda cliente: cliente.with_structured_output(self._esquema).invoke(mensajes, **kwargs)
        )


def contenido_texto(respuesta: object) -> str:
    """Extrae el texto de una respuesta del ChatModel. `content` puede ser
    un string plano (Gemini 2.x) o una lista de bloques
    `{'type': 'text', 'text': ...}` (confirmado con gemini-3.5-flash-lite
    contra la API real, 2026-09-10). Nunca asumir un formato fijo."""
    contenido = getattr(respuesta, "content", respuesta)
    if isinstance(contenido, list):
        return "".join(
            bloque.get("text", "")
            for bloque in contenido
            if isinstance(bloque, dict) and bloque.get("type") == "text"
        ).strip()
    return str(contenido).strip()


TIMEOUT_SEGUNDOS_LLM = 30
MAX_REINTENTOS_SDK = 1


def crear_rotador(configuracion: Configuracion | None = None) -> RotadorClavesGemini:
    """Factory principal. Usa la configuracion cargada de .env si no se pasa una.

    max_retries=1 y timeout bajo son deliberados (P-06 en DIFICULTADES.md):
    el SDK de google-genai reintenta un 429/503 con backoff exponencial
    propio (~1+2+4+8+16s) ANTES de que la excepcion llegue al rotador, asi
    que una key agotada tardaba hasta 42s en vez de fallar rapido y rotar.
    Con max_retries=1 el rotador es el unico que reintenta, y lo hace
    rotando de key (barato) en vez de reintentando la misma (caro)."""
    configuracion = configuracion or cargar_configuracion()
    if configuracion.llm_provider != "gemini":
        raise ValueError(f"Proveedor no soportado: {configuracion.llm_provider}")
    return RotadorClavesGemini(
        claves=configuracion.claves_gemini,
        modelo=configuracion.gemini_model,
        max_retries=MAX_REINTENTOS_SDK,
        timeout=TIMEOUT_SEGUNDOS_LLM,
    )
