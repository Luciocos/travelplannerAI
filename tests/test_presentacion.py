"""Tests de presentacion.py (D-19, tarjetas HTML en el chat). No toca la
red ni el LLM: solo construccion de strings."""

from __future__ import annotations

from asistente_viajes import presentacion as mod


def test_tarjeta_incluye_titulo_y_filas() -> None:
    html = mod.tarjeta("Mi título", ["fila uno", "fila dos"])

    assert "Mi título" in html
    # Desde D-22 las filas son divs flex, no <li>: se verifica el contenido
    # y que cada fila sea su propio bloque, no el markup exacto.
    assert "fila uno" in html
    assert "fila dos" in html
    assert html.count("display:flex") == 2


def test_tarjeta_descarta_filas_vacias() -> None:
    html = mod.tarjeta("Título", ["algo", "", None])  # type: ignore[list-item]

    assert html.count("display:flex") == 1
    assert "algo" in html


def test_tarjeta_agrega_el_pie_solo_si_se_pasa() -> None:
    sin_pie = mod.tarjeta("T", ["fila"])
    con_pie = mod.tarjeta("T", ["fila"], pie="nota al pie")

    assert "nota al pie" not in sin_pie
    assert "nota al pie" in con_pie


def test_escapar_neutraliza_tags_html() -> None:
    """Un nombre de actividad o una justificacion del LLM puede contener
    cualquier texto; escapar() tiene que dejarlo inerte antes de que se
    meta en una tarjeta HTML (XSS)."""
    peligroso = "<script>alert(1)</script>"

    escapado = mod.escapar(peligroso)

    assert "<script>" not in escapado
    assert "&lt;script&gt;" in escapado


def test_escapar_acepta_no_strings() -> None:
    assert mod.escapar(750000.0) == "750000.0"


def test_tarjeta_con_dato_escapado_no_deja_pasar_un_tag() -> None:
    html = mod.tarjeta("Actividades", [f"<strong>{mod.escapar('<img src=x>')}</strong>: buena"])

    assert "<img" not in html
    assert "&lt;img" in html


def test_texto_terminal_saca_las_etiquetas_y_desescapa() -> None:
    html = mod.tarjeta("Plan", ["Día 1: Museo &amp; Parque"])

    texto = mod.texto_terminal(html)

    assert "<div" not in texto
    assert "<li>" not in texto
    assert "Plan" in texto
    assert "- Día 1: Museo & Parque" in texto
