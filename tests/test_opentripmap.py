"""Tests del cliente de OpenTripMap. Mockea httpx, no toca la red ni
consume cuota (ver ci-y-git.md, ningun test toca la red)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from asistente_viajes.ingesta import opentripmap


def test_buscar_por_radio_devuelve_la_lista(monkeypatch: pytest.MonkeyPatch) -> None:
    lista_esperada = [{"xid": "N1", "name": "Lugar 1", "kinds": "museums"}]

    def get_falso(url, params, timeout):
        return httpx.Response(200, json=lista_esperada, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    resultado = opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000)

    assert resultado == lista_esperada


def test_buscar_por_radio_pasa_rate_y_limite_si_se_dan(monkeypatch: pytest.MonkeyPatch) -> None:
    parametros_capturados = {}

    def get_falso(url, params, timeout):
        parametros_capturados.update(params)
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000, limite=500, rate="1")

    assert parametros_capturados["rate"] == "1"
    assert parametros_capturados["limit"] == 500


def test_buscar_por_radio_sin_rate_no_lo_manda(monkeypatch: pytest.MonkeyPatch) -> None:
    parametros_capturados = {}

    def get_falso(url, params, timeout):
        parametros_capturados.update(params)
        return httpx.Response(200, json=[], request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000)

    assert "rate" not in parametros_capturados


def test_buscar_por_radio_propaga_error_como_error_opentripmap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_falso(url, params, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.buscar_por_radio("clave", lat=1.0, lon=2.0, radio_metros=5000)


def test_ingerir_destino_usa_cache_si_la_api_esta_caida(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directorio_raw = tmp_path / "raw"
    directorio_raw.mkdir()
    ruta_lista = directorio_raw / "salta_lista.json"
    ruta_lista.write_text(json.dumps([{"xid": "N1", "name": "Lugar 1"}]), encoding="utf-8")
    ruta_detalles = directorio_raw / "salta_detalles.json"
    ruta_detalles.write_text(
        json.dumps([{"xid": "N1", "name": "Lugar 1 detallado"}]), encoding="utf-8"
    )

    def buscar_falso(*args, **kwargs):
        raise opentripmap.ErrorOpenTripMap("caida simulada")

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    resultado = opentripmap.ingerir_destino(
        "Salta",
        lat=-24.79,
        lon=-65.41,
        radio_metros=5000,
        api_key="clave",
        directorio_raw=directorio_raw,
    )

    assert resultado == [{"xid": "N1", "name": "Lugar 1 detallado"}]


def test_geolocalizar_devuelve_el_lugar(monkeypatch: pytest.MonkeyPatch) -> None:
    lugar = {"name": "Rosario", "lat": -32.95, "lon": -60.66, "country": "AR"}

    def get_falso(url, params, timeout):
        return httpx.Response(200, json=lugar, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    assert opentripmap.geolocalizar("clave", "Rosario") == lugar


def test_geolocalizar_status_not_found_con_200_devuelve_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La API contesta 200 (no 404) con status NOT_FOUND cuando el lugar no
    existe. Confundir esto con un error de red seria el bug que
    _geolocalizar_seguro (destinos_bajo_demanda.py) existe para evitar."""

    def get_falso(url, params, timeout):
        return httpx.Response(
            200, json={"status": "NOT_FOUND"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", get_falso)

    assert opentripmap.geolocalizar("clave", "Narnia") is None


def test_geolocalizar_respuesta_vacia_devuelve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, params, timeout):
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    assert opentripmap.geolocalizar("clave", "Narnia") is None


def test_geolocalizar_sin_lat_devuelve_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url, params, timeout):
        return httpx.Response(200, json={"name": "Narnia"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    assert opentripmap.geolocalizar("clave", "Narnia") is None


def test_geolocalizar_propaga_error_de_red_como_error_opentripmap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_falso(url, params, timeout):
        raise httpx.ConnectError("caida simulada", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.geolocalizar("clave", "Rosario")


def test_obtener_detalle_reintenta_ante_429_y_despues_funciona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = {"n": 0}

    def get_falso(url, params, timeout):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            return httpx.Response(429, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"xid": "N1"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)
    monkeypatch.setattr(opentripmap.time, "sleep", lambda segundos: None)

    resultado = opentripmap.obtener_detalle("clave", "N1")

    assert resultado == {"xid": "N1"}
    assert llamadas["n"] == 2


def test_obtener_detalle_no_reintenta_ante_error_distinto_a_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = {"n": 0}

    def get_falso(url, params, timeout):
        llamadas["n"] += 1
        return httpx.Response(500, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)
    monkeypatch.setattr(opentripmap.time, "sleep", lambda segundos: None)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.obtener_detalle("clave", "N1")

    assert llamadas["n"] == 1


def test_obtener_detalle_agota_reintentos_y_levanta_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas = {"n": 0}

    def get_falso(url, params, timeout):
        llamadas["n"] += 1
        return httpx.Response(429, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)
    monkeypatch.setattr(opentripmap.time, "sleep", lambda segundos: None)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.obtener_detalle("clave", "N1")

    assert llamadas["n"] == opentripmap.REINTENTOS_POR_RATE_LIMIT + 1


def test_buscar_en_varios_puntos_intercala_por_punto(monkeypatch: pytest.MonkeyPatch) -> None:
    resultados_por_punto = {
        (1.0, 1.0): [{"xid": "A0"}, {"xid": "A1"}],
        (2.0, 2.0): [{"xid": "B0"}, {"xid": "B1"}],
    }

    def buscar_falso(api_key, lat, lon, radio_metros, kinds=None, limite=200, rate=None):
        return resultados_por_punto[(lat, lon)]

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    resultado = opentripmap.buscar_en_varios_puntos(
        "clave", puntos=[(1.0, 1.0), (2.0, 2.0)], radio_metros=5000, kinds=["museums"], limite_por_punto=10
    )

    assert [poi["xid"] for poi in resultado] == ["A0", "B0", "A1", "B1"]


def test_buscar_en_varios_puntos_deduplica_por_xid(monkeypatch: pytest.MonkeyPatch) -> None:
    resultados_por_punto = {
        (1.0, 1.0): [{"xid": "A0"}, {"xid": "COMPARTIDO"}],
        (2.0, 2.0): [{"xid": "COMPARTIDO"}, {"xid": "B0"}],
    }

    def buscar_falso(api_key, lat, lon, radio_metros, kinds=None, limite=200, rate=None):
        return resultados_por_punto[(lat, lon)]

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    resultado = opentripmap.buscar_en_varios_puntos(
        "clave", puntos=[(1.0, 1.0), (2.0, 2.0)], radio_metros=5000, kinds=["museums"], limite_por_punto=10
    )

    xids = [poi["xid"] for poi in resultado]
    assert sorted(xids) == ["A0", "B0", "COMPARTIDO"]
    assert len(xids) == 3


def test_buscar_en_varios_puntos_sigue_si_un_punto_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    def buscar_falso(api_key, lat, lon, radio_metros, kinds=None, limite=200, rate=None):
        if (lat, lon) == (1.0, 1.0):
            raise opentripmap.ErrorOpenTripMap("caida simulada")
        return [{"xid": "B0"}]

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    resultado = opentripmap.buscar_en_varios_puntos(
        "clave", puntos=[(1.0, 1.0), (2.0, 2.0)], radio_metros=5000, kinds=["museums"], limite_por_punto=10
    )

    assert [poi["xid"] for poi in resultado] == ["B0"]


def test_ruta_cruda_sin_grupo() -> None:
    ruta = opentripmap._ruta_cruda(Path("/tmp/raw"), "Buenos Aires", "lista")

    assert ruta == Path("/tmp/raw/buenos_aires_lista.json")


def test_ruta_cruda_con_grupo_separa_los_archivos() -> None:
    """`grupo` es lo que evita que ingerir comercios pise el archivo crudo
    de atractivos del mismo destino (mismo destino, mismo sufijo)."""
    ruta_atractivos = opentripmap._ruta_cruda(Path("/tmp/raw"), "Tokio", "lista", grupo="atractivos")
    ruta_comercios = opentripmap._ruta_cruda(Path("/tmp/raw"), "Tokio", "lista", grupo="comercios")

    assert ruta_atractivos == Path("/tmp/raw/tokio_atractivos_lista.json")
    assert ruta_comercios == Path("/tmp/raw/tokio_comercios_lista.json")
    assert ruta_atractivos != ruta_comercios


def test_ingerir_destino_con_grupo_no_pisa_la_ingesta_anterior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sin `grupo`, ingerir comercios despues de atractivos para el mismo
    destino escribia en el mismo archivo y la segunda ingesta pisaba a la
    primera (ver P-08/estado.md, caso real de Tokio)."""
    directorio_raw = tmp_path / "raw"

    def buscar_falso(api_key, lat, lon, radio_metros, kinds=None, limite=200, rate=None):
        return [{"xid": "N1"}]

    def obtener_falso(api_key, xid):
        return {"xid": xid, "kinds": ",".join(kinds_actuales)}

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)
    monkeypatch.setattr(opentripmap, "obtener_detalle", obtener_falso)

    kinds_actuales = ["museums"]
    opentripmap.ingerir_destino(
        "Tokio", lat=35.0, lon=139.0, radio_metros=5000, api_key="clave",
        directorio_raw=directorio_raw, grupo="atractivos",
    )
    kinds_actuales = ["foods"]
    opentripmap.ingerir_destino(
        "Tokio", lat=35.0, lon=139.0, radio_metros=5000, api_key="clave",
        directorio_raw=directorio_raw, grupo="comercios",
    )

    detalles_atractivos = json.loads(
        (directorio_raw / "tokio_atractivos_detalles.json").read_text(encoding="utf-8")
    )
    detalles_comercios = json.loads(
        (directorio_raw / "tokio_comercios_detalles.json").read_text(encoding="utf-8")
    )

    assert detalles_atractivos[0]["kinds"] == "museums"
    assert detalles_comercios[0]["kinds"] == "foods"


def test_ingerir_destino_relanza_si_no_hay_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directorio_raw = tmp_path / "raw"

    def buscar_falso(*args, **kwargs):
        raise opentripmap.ErrorOpenTripMap("caida simulada")

    monkeypatch.setattr(opentripmap, "buscar_por_radio", buscar_falso)

    with pytest.raises(opentripmap.ErrorOpenTripMap):
        opentripmap.ingerir_destino(
            "Salta",
            lat=-24.79,
            lon=-65.41,
            radio_metros=5000,
            api_key="clave",
            directorio_raw=directorio_raw,
        )
