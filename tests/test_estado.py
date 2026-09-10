"""Tests del modelo de estado y el merge no destructivo (RF2)."""

from __future__ import annotations

from datetime import date

from asistente_viajes.estado import PreferenciasViaje, fusionar_preferencias


def test_slots_faltantes_con_estado_vacio() -> None:
    estado = PreferenciasViaje()
    assert estado.slots_faltantes() == [
        "destino",
        "tipo_destino",
        "intereses",
        "presupuesto",
        "fecha_inicio",
        "fecha_fin",
        "cantidad_personas",
    ]
    assert not estado.completo()


def test_completo_cuando_no_faltan_slots() -> None:
    estado = PreferenciasViaje(
        destino="Miami",
        tipo_destino="playa",
        intereses=["compras"],
        presupuesto="medio",
        fecha_inicio=date(2026, 12, 1),
        fecha_fin=date(2026, 12, 10),
        cantidad_personas=2,
    )
    assert estado.completo()
    assert estado.slots_faltantes() == []


def test_intereses_vacia_cuenta_como_faltante() -> None:
    estado = PreferenciasViaje(intereses=[])
    assert "intereses" in estado.slots_faltantes()


def test_fusionar_no_pisa_un_slot_cargado_con_none() -> None:
    actual = PreferenciasViaje(destino="Miami", presupuesto="medio")
    nuevas = PreferenciasViaje(cantidad_personas=3)  # el resto viene None

    fusionado = fusionar_preferencias(actual, nuevas)

    assert fusionado.destino == "Miami"
    assert fusionado.presupuesto == "medio"
    assert fusionado.cantidad_personas == 3


def test_fusionar_permite_sobreescribir_con_valor_nuevo_explicito() -> None:
    actual = PreferenciasViaje(presupuesto="bajo")
    nuevas = PreferenciasViaje(presupuesto="alto")

    fusionado = fusionar_preferencias(actual, nuevas)

    assert fusionado.presupuesto == "alto"


def test_fusionar_intereses_reemplaza_lista_completa() -> None:
    actual = PreferenciasViaje(intereses=["historia"])
    nuevas = PreferenciasViaje(intereses=["historia", "caminatas"])

    fusionado = fusionar_preferencias(actual, nuevas)

    assert fusionado.intereses == ["historia", "caminatas"]
