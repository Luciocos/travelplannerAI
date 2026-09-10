"""Tests de config.py. No toca la red ni requiere Postgres real."""

from __future__ import annotations

import pytest

from asistente_viajes.config import ConfiguracionInvalida, cargar_configuracion


def _variables_base() -> dict[str, str]:
    return {
        "LLM_PROVIDER": "gemini",
        "GEMINI_MODEL": "gemini-2.5-flash-lite",
        "GEMINI_API_KEY_1": "clave-1",
        "GEMINI_API_KEY_2": "clave-2",
        "GEMINI_API_KEY_3": "clave-3",
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/test",
    }


def test_carga_configuracion_completa(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre, valor in _variables_base().items():
        monkeypatch.setenv(nombre, valor)

    configuracion = cargar_configuracion()

    assert configuracion.llm_provider == "gemini"
    assert configuracion.claves_gemini == ["clave-1", "clave-2", "clave-3"]


def test_falla_si_falta_una_variable_requerida(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre, valor in _variables_base().items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfiguracionInvalida):
        cargar_configuracion()


def test_falla_si_no_hay_ninguna_clave_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre, valor in _variables_base().items():
        if nombre.startswith("GEMINI_API_KEY_"):
            continue
        monkeypatch.setenv(nombre, valor)

    with pytest.raises(ConfiguracionInvalida):
        cargar_configuracion()
