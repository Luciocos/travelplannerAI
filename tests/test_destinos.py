"""Tests de destinos.py (lectura de data/reference/destinos.json). No
toca la red ni Postgres."""

from __future__ import annotations

from pathlib import Path

from asistente_viajes.destinos import buscar_destino_piloto, cargar_destinos_piloto


def _ruta_con(tmp_path: Path, contenido: str) -> Path:
    ruta = tmp_path / "destinos.json"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_cargar_destinos_piloto_ignora_metadata(tmp_path: Path) -> None:
    ruta = _ruta_con(
        tmp_path,
        '{"_comentario": "nota", "Cancun": {"pais": "Mexico", "lat": 21.1, "lon": -86.8}}',
    )

    destinos = cargar_destinos_piloto(ruta)

    assert list(destinos.keys()) == ["Cancun"]


def test_buscar_destino_piloto_devuelve_nombre_canonico_y_datos(tmp_path: Path) -> None:
    ruta = _ruta_con(tmp_path, '{"Cancun": {"pais": "Mexico", "lat": 21.1, "lon": -86.8}}')

    resultado = buscar_destino_piloto("Cancun", ruta)

    assert resultado == ("Cancun", {"pais": "Mexico", "lat": 21.1, "lon": -86.8})


def test_buscar_destino_piloto_insensible_a_tildes_y_mayusculas(tmp_path: Path) -> None:
    ruta = _ruta_con(tmp_path, '{"Cancun": {"pais": "Mexico", "lat": 21.1, "lon": -86.8}}')

    assert buscar_destino_piloto("cancún", ruta) is not None
    assert buscar_destino_piloto("CANCUN", ruta) is not None


def test_buscar_destino_piloto_desconocido_devuelve_none(tmp_path: Path) -> None:
    ruta = _ruta_con(tmp_path, "{}")

    assert buscar_destino_piloto("Narnia", ruta) is None
