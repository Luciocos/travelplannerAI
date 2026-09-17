"""Tests de recomendar_actividades y recomendar_locales (RF3, RF4),
llamadas directo sin agente (ver plan-de-fases.md, criterio de Fase 3).
Mockea la recuperacion y el LLM, no toca la red ni Postgres real.

Desde P-06/D-12, la justificacion de todos los resultados sale de UNA sola
llamada estructurada al LLM (ver justificacion.py), no de una llamada por
resultado."""

from __future__ import annotations

from unittest.mock import MagicMock

from asistente_viajes.justificacion import ItemJustificado, LoteJustificado
from asistente_viajes.recuperacion._consulta import ResultadoRecuperado
from asistente_viajes.tools import recomendar_actividades as mod_actividades
from asistente_viajes.tools import recomendar_locales as mod_locales
from asistente_viajes.tools import responder_faq_viajero as mod_faq
from asistente_viajes.tools.responder_faq_viajero import RespuestaFaq


def _rotador_con_lote(items: list[ItemJustificado]) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = LoteJustificado(items=items)
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    return rotador


def test_recomendar_actividades_justifica_solo_con_el_texto_recuperado(monkeypatch) -> None:
    resultado = ResultadoRecuperado(
        nombre="Museo de Arqueologia de Alta Montaña",
        categoria="museums",
        texto="Texto real recuperado del corpus.",
    )
    monkeypatch.setattr(mod_actividades, "buscar_atractivos", lambda *_, **__: [resultado])

    rotador = _rotador_con_lote(
        [ItemJustificado(indice=0, relevante=True, justificacion="Justificación de prueba.")]
    )
    actividades = mod_actividades.recomendar_actividades(
        conexion=MagicMock(), rotador=rotador, destino="Salta", intereses=["historia"]
    )

    assert len(actividades) == 1
    assert actividades[0].nombre == "Museo de Arqueologia de Alta Montaña"
    assert actividades[0].justificacion == "Justificación de prueba."

    prompt_enviado = rotador.con_salida_estructurada.return_value.invoke.call_args.args[0]
    assert "Texto real recuperado del corpus." in prompt_enviado
    assert "no agregue datos" in prompt_enviado.lower()


def test_recomendar_actividades_descarta_los_no_relevantes(monkeypatch) -> None:
    resultados = [
        ResultadoRecuperado(nombre="Lugar A", categoria="museums", texto="texto A"),
        ResultadoRecuperado(nombre="Lugar B", categoria="museums", texto="texto B"),
    ]
    monkeypatch.setattr(mod_actividades, "buscar_atractivos", lambda *_, **__: resultados)

    rotador = _rotador_con_lote(
        [
            ItemJustificado(indice=0, relevante=True, justificacion="Le va a interesar."),
            ItemJustificado(indice=1, relevante=False, justificacion=""),
        ]
    )
    actividades = mod_actividades.recomendar_actividades(
        conexion=MagicMock(), rotador=rotador, destino="Salta", intereses=["historia"]
    )

    assert len(actividades) == 1
    assert actividades[0].nombre == "Lugar A"


def test_recomendar_actividades_una_sola_llamada_al_llm_por_mas_resultados_que_haya(
    monkeypatch,
) -> None:
    resultados = [
        ResultadoRecuperado(nombre=f"Lugar {i}", categoria="museums", texto=f"texto {i}")
        for i in range(5)
    ]
    monkeypatch.setattr(mod_actividades, "buscar_atractivos", lambda *_, **__: resultados)

    rotador = _rotador_con_lote(
        [ItemJustificado(indice=i, relevante=True, justificacion="ok") for i in range(5)]
    )
    mod_actividades.recomendar_actividades(
        conexion=MagicMock(), rotador=rotador, destino="Salta", intereses=["historia"]
    )

    assert rotador.con_salida_estructurada.return_value.invoke.call_count == 1


def test_recomendar_locales_incluye_direccion_y_precio(monkeypatch) -> None:
    resultado = ResultadoRecuperado(
        nombre="Mercado Artesanal",
        categoria="shops",
        texto="Texto real del comercio.",
        direccion="Av. San Martin 2555",
        rango_precio="$$",
    )
    monkeypatch.setattr(mod_locales, "buscar_comercios", lambda *_, **__: [resultado])

    rotador = _rotador_con_lote(
        [
            ItemJustificado(
                indice=0, relevante=True, justificacion="Buena opción para lo que pediste."
            )
        ]
    )
    locales = mod_locales.recomendar_locales(
        conexion=MagicMock(), rotador=rotador, destino="Salta", consulta="artesanias"
    )

    assert len(locales) == 1
    assert locales[0].direccion == "Av. San Martin 2555"
    assert locales[0].rango_precio == "$$"


def test_tool_recomendar_actividades_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_actividades.crear_tool_recomendar_actividades(
        conexion=MagicMock(), rotador=_rotador_con_lote([])
    )

    assert tool_creada.name == "recomendar_actividades"
    assert tool_creada.description  # el agente lee esto para decidir cuando llamarla
    assert tool_creada.args_schema is mod_actividades.ArgsRecomendarActividades


def test_tool_recomendar_locales_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_locales.crear_tool_recomendar_locales(
        conexion=MagicMock(), rotador=_rotador_con_lote([])
    )

    assert tool_creada.name == "recomendar_locales"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_locales.ArgsRecomendarLocales


def _rotador_con_respuesta_faq(respuesta: RespuestaFaq) -> MagicMock:
    rotador = MagicMock()
    modelo_estructurado = MagicMock()
    modelo_estructurado.invoke.return_value = respuesta
    rotador.con_salida_estructurada.return_value = modelo_estructurado
    return rotador


def test_responder_faq_viajero_sintetiza_una_sola_respuesta(monkeypatch) -> None:
    resultado = ResultadoRecuperado(
        nombre="Taxis y tarifas",
        categoria="estafas",
        texto="Texto real del corpus de FAQ.",
    )
    monkeypatch.setattr(mod_faq, "buscar_faq", lambda *_, **__: [resultado])

    rotador = _rotador_con_respuesta_faq(
        RespuestaFaq(
            respondida=True,
            respuesta="En Cancun conviene acordar el precio antes de subir.",
            temas_usados=["Taxis y tarifas"],
        )
    )
    respuesta = mod_faq.responder_faq_viajero(
        conexion=MagicMock(), rotador=rotador, destino="Cancun", consulta="es seguro tomar un taxi"
    )

    assert respuesta.respondida is True
    assert respuesta.respuesta == "En Cancun conviene acordar el precio antes de subir."

    prompt_enviado = rotador.con_salida_estructurada.return_value.invoke.call_args.args[0]
    assert "Texto real del corpus de FAQ." in prompt_enviado
    assert "no agregue datos" in prompt_enviado.lower()


def test_responder_faq_viajero_sin_resultados_no_llama_al_llm(monkeypatch) -> None:
    monkeypatch.setattr(mod_faq, "buscar_faq", lambda *_, **__: [])
    rotador = MagicMock()

    respuesta = mod_faq.responder_faq_viajero(
        conexion=MagicMock(), rotador=rotador, destino="Cancun", consulta="algo sin datos"
    )

    assert respuesta.respondida is False
    rotador.con_salida_estructurada.assert_not_called()


def test_tool_responder_faq_viajero_tiene_docstring_y_args_schema() -> None:
    tool_creada = mod_faq.crear_tool_responder_faq_viajero(
        conexion=MagicMock(),
        rotador=_rotador_con_respuesta_faq(RespuestaFaq(respondida=False, respuesta="")),
    )

    assert tool_creada.name == "responder_faq_viajero"
    assert tool_creada.description
    assert tool_creada.args_schema is mod_faq.ArgsResponderFaqViajero
