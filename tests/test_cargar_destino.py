"""Tests de scripts/cargar_destino.py: combina data/raw (opentripmap) y
data/curated para un destino. No toca la red ni Postgres real, mockea
cargar_documentos."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scripts import cargar_destino as mod


def _detalle_opentripmap(nombre: str, kinds: str = "museums,historic") -> dict:
    return {
        "xid": f"N-{nombre}",
        "name": nombre,
        "kinds": kinds,
        "wikipedia_extracts": {"text": "x" * 250},
        "point": {"lat": 1.0, "lon": 2.0},
    }


def _registro_curado(destino: str, nombre: str) -> dict:
    return {
        "corpus": "atractivos",
        "destino": destino,
        "nombre": nombre,
        "categoria": "historic",
        "texto": "y" * 250,
        "fuente": "curado",
    }


def test_documentos_de_opentripmap_lee_el_detalle_del_destino(tmp_path: Path) -> None:
    ruta = tmp_path / "cancun_detalles.json"
    ruta.write_text(json.dumps([_detalle_opentripmap("El Meco")]), encoding="utf-8")

    documentos = mod._documentos_de_opentripmap("Cancun", tmp_path)

    assert len(documentos) == 1
    assert documentos[0].nombre == "El Meco"
    assert documentos[0].fuente == "opentripmap"


def test_documentos_de_opentripmap_sin_archivo_no_rompe(tmp_path: Path) -> None:
    documentos = mod._documentos_de_opentripmap("Cancun", tmp_path)

    assert documentos == []


def test_documentos_curados_filtra_por_destino_sin_importar_archivo(tmp_path: Path) -> None:
    ruta = tmp_path / "cualquier_nombre.json"
    ruta.write_text(
        json.dumps(
            [
                _registro_curado("Cancun", "Museo Maya de Cancun"),
                _registro_curado("Barcelona", "Sagrada Familia"),
            ]
        ),
        encoding="utf-8",
    )

    documentos = mod._documentos_curados("Cancun", tmp_path)

    assert len(documentos) == 1
    assert documentos[0].nombre == "Museo Maya de Cancun"
    assert documentos[0].fuente == "curado"


def test_main_combina_opentripmap_y_curados_y_llama_cargar_documentos(
    monkeypatch, tmp_path: Path
) -> None:
    directorio_raw = tmp_path / "raw"
    directorio_raw.mkdir()
    directorio_curated = tmp_path / "curated"
    directorio_curated.mkdir()

    (directorio_raw / "cancun_detalles.json").write_text(
        json.dumps([_detalle_opentripmap("El Meco")]), encoding="utf-8"
    )
    (directorio_curated / "cancun_atractivos.json").write_text(
        json.dumps([_registro_curado("Cancun", "Museo Maya de Cancun")]), encoding="utf-8"
    )

    monkeypatch.setattr(mod, "DIRECTORIO_RAW", directorio_raw)
    monkeypatch.setattr(mod, "DIRECTORIO_CURATED", directorio_curated)
    cargar_falso = MagicMock(return_value=2)
    monkeypatch.setattr(mod, "cargar_documentos", cargar_falso)
    monkeypatch.setattr("sys.argv", ["cargar_destino", "--destino", "Cancun"])

    codigo = mod.main()

    assert codigo == 0
    documentos_pasados = cargar_falso.call_args.args[0]
    assert {documento.nombre for documento in documentos_pasados} == {
        "El Meco",
        "Museo Maya de Cancun",
    }


def test_main_sin_documentos_devuelve_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "DIRECTORIO_RAW", tmp_path / "raw_vacio")
    monkeypatch.setattr(mod, "DIRECTORIO_CURATED", tmp_path / "curated_vacio")
    (tmp_path / "curated_vacio").mkdir()
    monkeypatch.setattr("sys.argv", ["cargar_destino", "--destino", "Narnia"])

    codigo = mod.main()

    assert codigo == 1
