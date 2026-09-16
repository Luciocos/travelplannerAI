"""Aisla los tests del `.env` real de quien los corre.

`config.py` llama `load_dotenv()` al importarse, así que cualquier
GEMINI_API_KEY_n / RAPIDAPI_* / etc. que ya esté cargado en el entorno
real de la máquina se filtra a `os.environ` y de ahí a los tests, aunque
un test individual nunca lo haya seteado. Sin esta limpieza, un test que
asume "no hay ninguna clave de Gemini" puede pasar o fallar según qué
`.env` tenga quien lo corre, no según la lógica que dice probar.
"""

from __future__ import annotations

import os
import re

import pytest

_PATRONES_A_LIMPIAR = [
    re.compile(r"^GEMINI_API_KEY(_\d+)?$"),
    re.compile(r"^RAPIDAPI_"),
    re.compile(
        r"^(LLM_PROVIDER|GEMINI_MODEL|GROQ_API_KEY|OPENTRIPMAP_API_KEY|DATABASE_URL|USE_FIXTURES)$"
    ),
]


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    for nombre in list(os.environ):
        if any(patron.match(nombre) for patron in _PATRONES_A_LIMPIAR):
            monkeypatch.delenv(nombre, raising=False)
