"""Carga de variables de entorno y constantes del proyecto.

Falla rapido y con mensaje claro si falta una variable requerida. La lista
de claves de Gemini se arma dinamicamente leyendo todas las variables que
matcheen GEMINI_API_KEY_<n>, sin cantidad hardcodeada (ver llm-y-claves.md).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

_PATRON_CLAVE_GEMINI = re.compile(r"^GEMINI_API_KEY_(\d+)$")

# Destinos piloto habilitados para esta entrega. Ver estado.md de la skill.
DESTINOS_HABILITADOS: list[str] = ["Europa", "Miami", "Caribe"]


class ConfiguracionInvalida(RuntimeError):
    """Falta una variable de entorno requerida o esta mal formada."""


def _variable_requerida(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise ConfiguracionInvalida(
            f"Falta la variable de entorno '{nombre}'. Revisa tu .env "
            f"(copialo desde .env.example si todavia no existe)."
        )
    return valor


def _claves_gemini() -> list[str]:
    claves: dict[int, str] = {}
    for nombre, valor in os.environ.items():
        coincidencia = _PATRON_CLAVE_GEMINI.match(nombre)
        if coincidencia and valor:
            claves[int(coincidencia.group(1))] = valor

    if not claves:
        raise ConfiguracionInvalida(
            "No se encontro ninguna variable GEMINI_API_KEY_<n> en el entorno. "
            "Se necesita al menos GEMINI_API_KEY_1."
        )

    return [claves[indice] for indice in sorted(claves)]


@dataclass(frozen=True)
class Configuracion:
    llm_provider: str
    gemini_model: str
    claves_gemini: list[str] = field(default_factory=list)
    database_url: str = ""
    opentripmap_api_key: str | None = None
    amadeus_client_id: str | None = None
    amadeus_client_secret: str | None = None


def cargar_configuracion() -> Configuracion:
    """Punto unico de lectura de configuracion. Falla rapido si algo falta."""
    return Configuracion(
        llm_provider=_variable_requerida("LLM_PROVIDER"),
        gemini_model=_variable_requerida("GEMINI_MODEL"),
        claves_gemini=_claves_gemini(),
        database_url=_variable_requerida("DATABASE_URL"),
        opentripmap_api_key=os.environ.get("OPENTRIPMAP_API_KEY") or None,
        amadeus_client_id=os.environ.get("AMADEUS_CLIENT_ID") or None,
        amadeus_client_secret=os.environ.get("AMADEUS_CLIENT_SECRET") or None,
    )
