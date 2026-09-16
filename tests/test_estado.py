"""Tests del modelo de estado y el merge no destructivo (RF2)."""

from __future__ import annotations

from datetime import date

from asistente_viajes.estado import (
    DURACION_MAXIMA_DIAS,
    PreferenciasViaje,
    detectar_cambios,
    fusionar_preferencias,
    normalizar_presupuesto,
    validar_preferencias,
)


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


def test_tipo_destino_deja_de_ser_obligatorio_con_destino_confirmado() -> None:
    """D-14: para un destino piloto (Barcelona, Miami, Cancun) el tipo de
    destino se deriva de destinos.json, no tiene sentido volver a
    preguntarlo."""
    estado = PreferenciasViaje(destino="Barcelona")
    assert "tipo_destino" not in estado.slots_faltantes()


def test_tipo_destino_sigue_faltando_sin_destino() -> None:
    estado = PreferenciasViaje()
    assert "tipo_destino" in estado.slots_faltantes()


def test_duracion_dias_reemplaza_a_las_fechas_exactas() -> None:
    """D-14: un plan puede armarse con 'X dias, fecha a confirmar', no
    hace falta esperar fechas de calendario exactas."""
    estado = PreferenciasViaje(
        destino="Cancun",
        tipo_destino="playa",
        intereses=["playa"],
        presupuesto="medio",
        cantidad_personas=2,
        duracion_dias=7,
    )
    assert estado.tiene_cuando() is True
    assert estado.completo() is True
    assert "fecha_inicio" not in estado.slots_faltantes()
    assert "fecha_fin" not in estado.slots_faltantes()


def test_sin_fechas_ni_duracion_faltan_fecha_inicio_y_fecha_fin() -> None:
    estado = PreferenciasViaje()
    assert estado.tiene_cuando() is False
    assert "fecha_inicio" in estado.slots_faltantes()
    assert "fecha_fin" in estado.slots_faltantes()


def test_normalizar_presupuesto_mapea_sinonimos() -> None:
    assert normalizar_presupuesto("economico") == "bajo"
    assert normalizar_presupuesto("Lujo") == "alto"
    assert normalizar_presupuesto("moderado") == "medio"


def test_normalizar_presupuesto_deja_pasar_valor_ya_valido() -> None:
    assert normalizar_presupuesto("medio") == "medio"
    assert normalizar_presupuesto(None) is None


def test_validar_preferencias_detecta_fecha_pasada() -> None:
    estado = PreferenciasViaje(fecha_inicio=date(2020, 1, 1), fecha_fin=date(2020, 1, 5))
    errores = validar_preferencias(estado, hoy=date(2026, 9, 16))
    assert any("ya paso" in error for error in errores)


def test_validar_preferencias_detecta_fin_antes_que_inicio() -> None:
    estado = PreferenciasViaje(fecha_inicio=date(2027, 1, 10), fecha_fin=date(2027, 1, 5))
    errores = validar_preferencias(estado, hoy=date(2026, 9, 16))
    assert any("anterior" in error for error in errores)


def test_validar_preferencias_detecta_viaje_demasiado_largo() -> None:
    estado = PreferenciasViaje(duracion_dias=DURACION_MAXIMA_DIAS + 1)
    errores = validar_preferencias(estado, hoy=date(2026, 9, 16))
    assert any(str(DURACION_MAXIMA_DIAS) in error for error in errores)


def test_validar_preferencias_detecta_cantidad_personas_invalida() -> None:
    estado = PreferenciasViaje(cantidad_personas=0)
    assert validar_preferencias(estado, hoy=date(2026, 9, 16))

    estado = PreferenciasViaje(cantidad_personas=25)
    assert validar_preferencias(estado, hoy=date(2026, 9, 16))


def test_validar_preferencias_sin_errores_con_datos_validos() -> None:
    estado = PreferenciasViaje(
        fecha_inicio=date(2027, 1, 10), fecha_fin=date(2027, 1, 15), cantidad_personas=2
    )
    assert validar_preferencias(estado, hoy=date(2026, 9, 16)) == []


def test_detectar_cambios_encuentra_campos_que_afectan_el_plan() -> None:
    anterior = PreferenciasViaje(destino="Cancun", cantidad_personas=2)
    nuevo = PreferenciasViaje(destino="Cancun", cantidad_personas=3)

    assert detectar_cambios(anterior, nuevo) == {"cantidad_personas"}


def test_detectar_cambios_vacio_si_nada_cambio() -> None:
    estado = PreferenciasViaje(destino="Cancun", cantidad_personas=2)
    assert detectar_cambios(estado, estado.model_copy()) == set()
