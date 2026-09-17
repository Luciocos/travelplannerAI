"""Tarjetas HTML para los resultados que arma el orquestador (D-19).

La UI (ui/chat_app.py) renderiza cada fragmento con
`st.markdown(..., unsafe_allow_html=True)`, así que cualquier texto que
pueda venir de una fuente externa o del LLM (nombre de un lugar, una
justificación de RAG) tiene que pasar por escapar() antes de entrar a una
plantilla HTML: nunca se interpola un dato dinámico directo en el markup
(XSS). El CLI (scripts/chat.py) recibe el mismo texto con las etiquetas
crudas; no vale la pena mantener dos formatos en paralelo para una tool de
demo secundaria (ver arquitectura.md sobre el notebook como entregable
oficial).
"""

from __future__ import annotations

import html as _html
import re

_ESTILO_TARJETA = (
    "border:1px solid rgba(120,120,120,0.35);"
    "border-radius:10px;padding:0.75rem 1rem;margin:0.4rem 0;"
    "background:rgba(120,120,120,0.08);"
)
_ESTILO_TITULO = "font-weight:600;margin-bottom:0.35rem;"
_ESTILO_LISTA = "margin:0;padding-left:1.1rem;"
_ESTILO_PIE = "font-size:0.85em;opacity:0.75;margin-top:0.4rem;"


def escapar(valor: object) -> str:
    """Escapa cualquier valor dinámico antes de meterlo en una plantilla
    HTML. Acepta no-strings (números, etc) por comodidad de los llamadores."""
    return _html.escape(str(valor))


def tarjeta(titulo: str, filas: list[str], pie: str | None = None) -> str:
    """Tarjeta HTML genérica: título + lista de filas.

    `titulo`, `filas` y `pie` ya tienen que venir armados (texto dinámico
    ya escapado por el llamador, mezclado con markup propio como
    <strong> si hace falta). Filas vacías se descartan."""
    items = "".join(f"<li>{fila}</li>" for fila in filas if fila)
    pie_html = f'<div style="{_ESTILO_PIE}">{pie}</div>' if pie else ""
    return (
        f'<div style="{_ESTILO_TARJETA}">'
        f'<div style="{_ESTILO_TITULO}">{titulo}</div>'
        f'<ul style="{_ESTILO_LISTA}">{items}</ul>'
        f"{pie_html}"
        f"</div>"
    )


_ETIQUETA_LI = re.compile(r"<li>")
_ETIQUETA_CUALQUIERA = re.compile(r"<[^>]+>")


def texto_terminal(html_o_texto: str) -> str:
    """Fallback legible para una terminal (scripts/chat.py, que no
    interpreta HTML): saca el markup de una tarjeta y desescapa las
    entidades, conservando un guion por fila."""
    con_guiones = _ETIQUETA_LI.sub("\n- ", html_o_texto)
    sin_etiquetas = _ETIQUETA_CUALQUIERA.sub("", con_guiones)
    return _html.unescape(sin_etiquetas).strip()
