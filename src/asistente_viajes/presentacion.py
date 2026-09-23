"""Tarjetas HTML para los resultados que arma el orquestador (D-20, D-22).

La UI (ui/chat_app.py) renderiza cada fragmento con
`st.markdown(..., unsafe_allow_html=True)`, así que cualquier texto que
pueda venir de una fuente externa o del LLM (nombre de un lugar, una
justificación de RAG) tiene que pasar por escapar() antes de entrar a una
plantilla HTML: nunca se interpola un dato dinámico directo en el markup
(XSS). El CLI (scripts/chat.py) recibe el mismo texto con las etiquetas
crudas; no vale la pena mantener dos formatos en paralelo para una tool de
demo secundaria (ver arquitectura.md sobre el notebook como entregable
oficial).

Desde D-22 estas tarjetas son SOLO los datos duros: la prosa del turno la
escribe el LLM (ver PROMPT_REDACTAR) y se muestra arriba de la tarjeta. Por
eso acá conviene que se lean como una tabla, no como un párrafo.

Los colores salen de `currentColor` y de transparencias sobre el fondo, no
de literales: Streamlit puede estar en tema claro u oscuro y la tarjeta
tiene que servir en los dos. Tampoco se usan emoji como iconos: dependen de
la fuente del sistema y en Chrome/macOS se renderizaban vacíos (mismo bug
que tenían los botones de la sidebar).
"""

from __future__ import annotations

import html as _html
import re

_BORDE = "1px solid rgba(128,128,128,0.3)"

_ESTILO_TARJETA = (
    f"border:{_BORDE};border-radius:12px;margin:0.5rem 0;"
    "background:rgba(128,128,128,0.06);overflow:hidden;"
)
_ESTILO_TITULO = (
    "font-weight:600;font-size:0.95rem;letter-spacing:0.01em;"
    "padding:0.6rem 0.9rem;background:rgba(128,128,128,0.10);"
    f"border-bottom:{_BORDE};"
)
_ESTILO_FILA = f"display:flex;gap:0.75rem;padding:0.55rem 0.9rem;border-bottom:{_BORDE};"
_ESTILO_FILA_ULTIMA = "display:flex;gap:0.75rem;padding:0.55rem 0.9rem;"
_ESTILO_ETIQUETA = "flex:0 0 5.5rem;font-weight:600;font-size:0.85rem;opacity:0.75;"
_ESTILO_CUERPO = "flex:1 1 auto;min-width:0;font-size:0.9rem;"
_ESTILO_MONTO = "flex:0 0 auto;font-variant-numeric:tabular-nums;opacity:0.8;font-size:0.85rem;"
_ESTILO_PIE = (
    "font-size:0.8rem;opacity:0.7;padding:0.5rem 0.9rem;"
    f"border-top:{_BORDE};background:rgba(128,128,128,0.06);"
)


def escapar(valor: object) -> str:
    """Escapa cualquier valor dinámico antes de meterlo en una plantilla
    HTML. Acepta no-strings (números, etc) por comodidad de los llamadores."""
    return _html.escape(str(valor))


def _fila(cuerpo: str, etiqueta: str | None, monto: str | None, ultima: bool) -> str:
    estilo = _ESTILO_FILA_ULTIMA if ultima else _ESTILO_FILA
    partes = []
    if etiqueta:
        partes.append(f'<div style="{_ESTILO_ETIQUETA}">{etiqueta}</div>')
    partes.append(f'<div style="{_ESTILO_CUERPO}">{cuerpo}</div>')
    if monto:
        partes.append(f'<div style="{_ESTILO_MONTO}">{monto}</div>')
    return f'<div style="{estilo}">{"".join(partes)}</div>'


def tarjeta(titulo: str, filas: list[str], pie: str | None = None) -> str:
    """Tarjeta simple: título + una fila por ítem.

    `titulo`, `filas` y `pie` ya tienen que venir armados (texto dinámico
    ya escapado por el llamador, mezclado con markup propio como
    <strong> si hace falta). Filas vacías se descartan."""
    return tarjeta_detallada(titulo, [{"cuerpo": fila} for fila in filas if fila], pie)


def tarjeta_detallada(
    titulo: str, filas: list[dict[str, str | None]], pie: str | None = None
) -> str:
    """Tarjeta con filas de hasta tres columnas: una etiqueta a la
    izquierda (el día, por ejemplo), el cuerpo, y un monto alineado a la
    derecha. Es lo que hace que un itinerario se lea como un itinerario y
    no como una lista de viñetas.

    Cada fila es un dict con 'cuerpo' y, opcionalmente, 'etiqueta' y
    'monto'. Todo ya escapado por el llamador."""
    visibles = [fila for fila in filas if fila.get("cuerpo")]
    if not visibles:
        return ""

    cuerpo_html = "".join(
        _fila(
            fila["cuerpo"],
            fila.get("etiqueta"),
            fila.get("monto"),
            ultima=(indice == len(visibles) - 1) and not pie,
        )
        for indice, fila in enumerate(visibles)
    )
    pie_html = f'<div style="{_ESTILO_PIE}">{pie}</div>' if pie else ""
    return (
        f'<div style="{_ESTILO_TARJETA}">'
        f'<div style="{_ESTILO_TITULO}">{titulo}</div>'
        f"{cuerpo_html}{pie_html}"
        f"</div>"
    )


# El <div> de cada fila abre con `display:flex` (ver _ESTILO_FILA). El
# patron matchea la etiqueta COMPLETA, no su prefijo: consumir solo
# `<div style="display:flex` dejaba el resto del CSS (`;gap:0.75rem;...">`)
# como texto suelto, porque ya no empezaba con `<` y el limpiador generico
# de etiquetas no lo reconocia.
_INICIO_DE_FILA = re.compile(r'<(?:div style="display:flex[^>]*|li)>')
_ETIQUETA_CUALQUIERA = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"[ \t]+")


def texto_terminal(html_o_texto: str) -> str:
    """Fallback legible para una terminal (scripts/chat.py, que no
    interpreta HTML): saca el markup de una tarjeta y desescapa las
    entidades, conservando un salto por fila."""
    con_saltos = _INICIO_DE_FILA.sub("\n- ", html_o_texto)
    sin_etiquetas = _ETIQUETA_CUALQUIERA.sub(" ", con_saltos)
    lineas = (_ESPACIOS.sub(" ", linea).strip() for linea in sin_etiquetas.splitlines())
    return _html.unescape("\n".join(linea for linea in lineas if linea)).strip()
