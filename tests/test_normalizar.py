"""Tests de normalizacion. No tocan la red."""

from __future__ import annotations

from asistente_viajes.ingesta.normalizar import (
    LONGITUD_MINIMA_TEXTO,
    _slug_curado,
    normalizar_curado,
    normalizar_poi_opentripmap,
)


def _detalle_valido(texto: str = "x" * LONGITUD_MINIMA_TEXTO) -> dict:
    return {
        "xid": "N123",
        "name": "Museo de Arqueologia de Alta Montana",
        "kinds": "museums,historic",
        "wikipedia_extracts": {"text": texto},
        "point": {"lat": -24.789, "lon": -65.41},
        "address": {"road": "Calle Falsa 123", "city": "Salta"},
    }


def test_normaliza_poi_con_texto_suficiente() -> None:
    documento = normalizar_poi_opentripmap(_detalle_valido(), destino="Salta")

    assert documento is not None
    assert documento.corpus == "atractivos"
    assert documento.fuente == "opentripmap"
    assert documento.xid == "N123"
    assert documento.direccion == "Calle Falsa 123, Salta"


def test_descarta_poi_con_texto_corto() -> None:
    detalle = _detalle_valido(texto="muy corto")
    assert normalizar_poi_opentripmap(detalle, destino="Salta") is None


def test_descarta_poi_sin_kind_conocido() -> None:
    detalle = _detalle_valido()
    detalle["kinds"] = "other,interesting_places"
    assert normalizar_poi_opentripmap(detalle, destino="Salta") is None


def test_clasifica_comercios_por_kind() -> None:
    detalle = _detalle_valido()
    detalle["kinds"] = "foods,restaurants"
    documento = normalizar_poi_opentripmap(detalle, destino="Salta")

    assert documento is not None
    assert documento.corpus == "comercios"


def test_descarta_poi_con_kind_primario_excluido() -> None:
    """P-08: torres de departamentos/hoteles con kind primario 'skyscrapers'
    o 'resorts' se descartan aunque tengan 'architecture' como kind
    secundario (Miami: 49 de 75 'atractivos' eran edificios residenciales)."""
    detalle = _detalle_valido()
    detalle["kinds"] = "skyscrapers,architecture,interesting_places"
    assert normalizar_poi_opentripmap(detalle, destino="Miami") is None

    detalle["kinds"] = "resorts,accomodations,skyscrapers,architecture"
    assert normalizar_poi_opentripmap(detalle, destino="Miami") is None


def test_no_descarta_atractivo_real_con_architecture_secundario() -> None:
    detalle = _detalle_valido()
    detalle["kinds"] = "historic,architecture,interesting_places"
    documento = normalizar_poi_opentripmap(detalle, destino="Barcelona")
    assert documento is not None


def test_normaliza_registro_curado() -> None:
    registro = {
        "corpus": "comercios",
        "destino": "Salta",
        "nombre": "Mercado Artesanal",
        "categoria": "shops",
        "texto": "Mercado tradicional de artesanias salteñas.",
        "direccion": "Av. San Martin 2555",
        "rango_precio": "$$",
    }

    documento = normalizar_curado(registro)

    assert documento.fuente == "curado"
    assert documento.xid == "curado-comercios-salta-mercado-artesanal"


def test_normaliza_registro_curado_respeta_xid_explicito() -> None:
    registro = {
        "corpus": "faq",
        "destino": "Cancun",
        "nombre": "Seguridad",
        "texto": "texto",
        "xid": "faq-cancun-seguridad-manual",
    }

    documento = normalizar_curado(registro)

    assert documento.xid == "faq-cancun-seguridad-manual"


def test_slug_curado_es_estable_y_sin_tildes_ni_espacios() -> None:
    slug = _slug_curado("atractivos", "Cancún", "Museo Maya de Cancún")
    assert slug == "curado-atractivos-cancun-museo-maya-de-cancun"
    assert _slug_curado("atractivos", "Cancún", "Museo Maya de Cancún") == slug
