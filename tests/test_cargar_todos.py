"""Tests de scripts/cargar_todos.py. No toca la red ni Postgres real:
mockea obtener_conexion, documentos_de_destino y cargar_documentos."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from asistente_viajes.ingesta.normalizar import DocumentoCorpus
from scripts import cargar_todos as mod


def _documento(destino: str) -> DocumentoCorpus:
    return DocumentoCorpus(corpus="atractivos", destino=destino, texto="x" * 250, fuente="curado")


@contextmanager
def _con_conexion(conexion):
    yield conexion


def test_main_carga_cada_destino_piloto(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Barcelona": {}, "Miami": {}})
    monkeypatch.setattr(
        mod, "documentos_de_destino", lambda destino: [_documento(destino), _documento(destino)]
    )
    cargar_falso = MagicMock(return_value=2)
    monkeypatch.setattr(mod, "cargar_documentos", cargar_falso)
    monkeypatch.setattr("sys.argv", ["cargar_todos"])

    codigo = mod.main()

    assert codigo == 0
    assert cargar_falso.call_count == 2


def test_main_reemplazar_borra_antes_de_cargar(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Cancun": {}})
    monkeypatch.setattr(mod, "documentos_de_destino", lambda destino: [_documento(destino)])
    monkeypatch.setattr(mod, "cargar_documentos", lambda documentos: len(documentos))
    borrar_llamado = MagicMock(return_value=5)
    monkeypatch.setattr(mod, "_borrar_destino", borrar_llamado)
    monkeypatch.setattr("sys.argv", ["cargar_todos", "--reemplazar"])

    codigo = mod.main()

    assert codigo == 0
    borrar_llamado.assert_called_once_with("Cancun")


def test_main_sin_reemplazar_no_borra(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Cancun": {}})
    monkeypatch.setattr(mod, "documentos_de_destino", lambda destino: [_documento(destino)])
    monkeypatch.setattr(mod, "cargar_documentos", lambda documentos: len(documentos))
    borrar_llamado = MagicMock()
    monkeypatch.setattr(mod, "_borrar_destino", borrar_llamado)
    monkeypatch.setattr("sys.argv", ["cargar_todos"])

    mod.main()

    borrar_llamado.assert_not_called()


def test_borrar_destino_ejecuta_delete_con_el_destino(monkeypatch) -> None:
    conexion = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 3
    conexion.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(mod, "obtener_conexion", lambda: _con_conexion(conexion))

    borradas = mod._borrar_destino("Cancun")

    assert borradas == 3
    parametros = cursor.execute.call_args.args[1]
    assert parametros["destino"] == "Cancun"


def test_main_destino_sin_documentos_sigue_con_los_demas(monkeypatch) -> None:
    monkeypatch.setattr(mod, "cargar_destinos_piloto", lambda: {"Cancun": {}, "Miami": {}})
    monkeypatch.setattr(
        mod,
        "documentos_de_destino",
        lambda destino: [] if destino == "Cancun" else [_documento(destino)],
    )
    cargar_falso = MagicMock(return_value=1)
    monkeypatch.setattr(mod, "cargar_documentos", cargar_falso)
    monkeypatch.setattr("sys.argv", ["cargar_todos"])

    codigo = mod.main()

    assert codigo == 0
    cargar_falso.assert_called_once()
