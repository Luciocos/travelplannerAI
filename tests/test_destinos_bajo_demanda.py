"""Tests de destinos_bajo_demanda.py (Fase 7E, D-23). No toca la red ni
Postgres: se mockea la conexion y las funciones de opentripmap.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from asistente_viajes import destinos_bajo_demanda as mod
from asistente_viajes.ingesta.opentripmap import ErrorOpenTripMap


def _conexion(fetchall_secuencia: list, fetchone_valor: tuple | None = None) -> MagicMock:
    """Conexion falsa: cada llamada a _conteo_por_corpus consume el
    siguiente elemento de `fetchall_secuencia` (una lista de filas
    (corpus, cantidad)); _nombre_canonico siempre devuelve `fetchone_valor`."""
    conexion = MagicMock()
    cursor = conexion.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = list(fetchall_secuencia)
    cursor.fetchone.return_value = fetchone_valor
    return conexion


# --- asegurar_destino: camino 1, ya tiene corpus ---------------------------


def test_asegurar_destino_piloto_con_corpus_no_toca_la_red(monkeypatch: pytest.MonkeyPatch) -> None:
    conexion = _conexion([[("atractivos", 12)]], fetchone_valor=("Cancun",))
    monkeypatch.setattr(
        mod, "buscar_destino_piloto", lambda destino: ("Cancun", {"lat": 21.1, "lon": -86.8, "pais": "MX"})
    )
    geolocalizar_falso = MagicMock()
    monkeypatch.setattr(mod, "geolocalizar", geolocalizar_falso)

    resultado = mod.asegurar_destino(conexion, "cancun")

    assert resultado is not None
    assert resultado.nombre == "Cancun"
    assert (resultado.lat, resultado.lon, resultado.pais) == (21.1, -86.8, "MX")
    assert resultado.atractivos == 12
    assert resultado.recien_ingerido is False
    geolocalizar_falso.assert_not_called()


def test_asegurar_destino_no_piloto_con_corpus_reresuelve_coordenadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comportamiento real y documentado (no un bug): un destino ingerido
    bajo demanda no tiene sus coordenadas guardadas en la base, asi que
    aunque ya tenga corpus se vuelven a resolver via geoname para poder
    informar RF8 (clima). Ver el comentario en asegurar_destino."""
    conexion = _conexion([[("atractivos", 7)]], fetchone_valor=("Salta",))
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)
    monkeypatch.setattr(
        mod,
        "geolocalizar",
        lambda api_key, nombre: {"lat": -24.79, "lon": -65.41, "country": "AR", "name": "Salta"},
    )
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")

    resultado = mod.asegurar_destino(conexion, "salta")

    assert (resultado.lat, resultado.lon, resultado.pais) == (-24.79, -65.41, "AR")
    assert resultado.atractivos == 7


def test_asegurar_destino_no_piloto_con_corpus_sin_api_key_no_rompe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexion = _conexion([[("atractivos", 7)]], fetchone_valor=("Salta",))
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)

    resultado = mod.asegurar_destino(conexion, "salta")

    assert (resultado.lat, resultado.lon, resultado.pais) == (0.0, 0.0, None)
    assert resultado.atractivos == 7


# --- asegurar_destino: camino 2, destino piloto sin corpus -----------------


def test_asegurar_destino_piloto_sin_corpus_ingiere_con_coordenadas_curadas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexion = _conexion([[], [("atractivos", 3)]])
    monkeypatch.setattr(
        mod, "buscar_destino_piloto", lambda destino: ("Cancun", {"lat": 21.1, "lon": -86.8, "pais": "MX"})
    )
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")
    ingerir_falso = MagicMock()
    monkeypatch.setattr(mod, "_ingerir", ingerir_falso)

    resultado = mod.asegurar_destino(conexion, "cancun")

    ingerir_falso.assert_called_once_with("Cancun", 21.1, -86.8, "clave")
    assert resultado.recien_ingerido is True
    assert resultado.atractivos == 3
    assert (resultado.lat, resultado.lon) == (21.1, -86.8)


def test_asegurar_destino_piloto_sin_corpus_y_sin_api_key_no_ingiere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conexion = _conexion([[]])
    monkeypatch.setattr(
        mod, "buscar_destino_piloto", lambda destino: ("Cancun", {"lat": 21.1, "lon": -86.8, "pais": "MX"})
    )
    ingerir_falso = MagicMock()
    monkeypatch.setattr(mod, "_ingerir", ingerir_falso)

    resultado = mod.asegurar_destino(conexion, "cancun")

    ingerir_falso.assert_not_called()
    assert resultado.recien_ingerido is False
    assert resultado.atractivos == 0


# --- asegurar_destino: camino 3, geolocalizar e ingerir --------------------


def test_asegurar_destino_nuevo_se_geolocaliza_e_ingiere(monkeypatch: pytest.MonkeyPatch) -> None:
    conexion = _conexion([[], [("atractivos", 5)]])
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)
    monkeypatch.setattr(
        mod, "geolocalizar", lambda api_key, nombre: {"lat": 35.0, "lon": 135.7, "country": "JP", "name": "Kioto"}
    )
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")
    ingerir_falso = MagicMock()
    monkeypatch.setattr(mod, "_ingerir", ingerir_falso)

    resultado = mod.asegurar_destino(conexion, "kioto")

    ingerir_falso.assert_called_once_with("Kioto", 35.0, 135.7, "clave")
    assert resultado.recien_ingerido is True
    assert resultado.pais == "JP"


def test_asegurar_destino_inexistente_devuelve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    conexion = _conexion([[]])
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)
    monkeypatch.setattr(mod, "geolocalizar", lambda api_key, nombre: None)
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")

    assert mod.asegurar_destino(conexion, "Narnia") is None


def test_asegurar_destino_no_confunde_no_verificable_con_inexistente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El bug real que este modulo evita (ver docstring del modulo y de
    NO_VERIFICABLE): sin API key, TODOS los destinos pasaban a ser
    inexistentes. Sin poder verificar, se sigue con el destino tal como lo
    dijo el cliente, no se lo declara inexistente."""
    conexion = _conexion([[]])
    monkeypatch.setattr(mod, "buscar_destino_piloto", lambda destino: None)
    # sin OPENTRIPMAP_API_KEY en el entorno (conftest ya lo limpia)

    resultado = mod.asegurar_destino(conexion, "Rosario")

    assert resultado is not None
    assert resultado.nombre == "Rosario"
    assert resultado.atractivos == 0
    assert resultado.recien_ingerido is False


# --- _geolocalizar_seguro: los tres estados ---------------------------------


def test_geolocalizar_seguro_sin_api_key_es_no_verificable() -> None:
    assert mod._geolocalizar_seguro("Rosario") is mod.NO_VERIFICABLE


def test_geolocalizar_seguro_devuelve_el_lugar_encontrado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")
    monkeypatch.setattr(mod, "geolocalizar", lambda api_key, nombre: {"lat": 1.0, "lon": 2.0})

    assert mod._geolocalizar_seguro("Rosario") == {"lat": 1.0, "lon": 2.0}


def test_geolocalizar_seguro_devuelve_none_si_el_geocoder_dice_que_no_existe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")
    monkeypatch.setattr(mod, "geolocalizar", lambda api_key, nombre: None)

    assert mod._geolocalizar_seguro("Narnia") is None


def test_geolocalizar_seguro_ante_error_de_red_es_no_verificable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENTRIPMAP_API_KEY", "clave")

    def geolocalizar_falso(api_key: str, nombre: str) -> dict:
        raise ErrorOpenTripMap("caida simulada")

    monkeypatch.setattr(mod, "geolocalizar", geolocalizar_falso)

    assert mod._geolocalizar_seguro("Rosario") is mod.NO_VERIFICABLE


def test_geolocalizar_seguro_no_verificable_es_distinto_de_inexistente() -> None:
    """None e NO_VERIFICABLE tienen que ser objetos distintos: confundirlos
    es exactamente el bug que este centinela existe para evitar."""
    assert mod.NO_VERIFICABLE is not None


# --- _puntaje_relevancia ----------------------------------------------------


def test_puntaje_relevancia_suma_por_tener_imagen() -> None:
    sin_imagen = mod._puntaje_relevancia({"rate": "1"})
    con_preview = mod._puntaje_relevancia({"rate": "1", "preview": {"source": "x"}})
    con_image = mod._puntaje_relevancia({"rate": "1", "image": "http://x"})

    assert con_preview - sin_imagen == pytest.approx(4.0)
    assert con_image - sin_imagen == pytest.approx(4.0)


def test_puntaje_relevancia_rate_con_sufijo_h_suma_bonus_de_patrimonio() -> None:
    normal = mod._puntaje_relevancia({"rate": "3"})
    patrimonio = mod._puntaje_relevancia({"rate": "3h"})

    assert patrimonio - normal == pytest.approx(5.0)


def test_puntaje_relevancia_rate_ausente_no_rompe() -> None:
    assert mod._puntaje_relevancia({}) == pytest.approx(0.0)


def test_puntaje_relevancia_suma_por_largo_de_extracto_con_tope() -> None:
    corto = mod._puntaje_relevancia({"wikipedia_extracts": {"text": "x" * 100}})
    largo = mod._puntaje_relevancia({"wikipedia_extracts": {"text": "x" * 4000}})

    assert corto == pytest.approx(0.25)
    assert largo == pytest.approx(6.0)


def test_puntaje_relevancia_suma_por_cantidad_de_kinds_con_tope() -> None:
    pocos = mod._puntaje_relevancia({"kinds": "museums,historic"})
    muchos = mod._puntaje_relevancia(
        {
            "kinds": "museums,historic,cultural,architecture,religion,natural,"
            "urban_environment,amusements"
        }
    )

    assert pocos == pytest.approx(0.6)
    assert muchos == pytest.approx(2.0)
