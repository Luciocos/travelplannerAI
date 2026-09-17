"""Todos los prompts del LLM, como constantes con nombre. Se citan en la
defensa, por eso viven en un solo lugar y no inline en medio de la logica
(ver ci-y-git.md, convenciones de trabajo).
"""

from __future__ import annotations

PROMPT_EXTRAER_SLOTS = """\
Extraé del mensaje del usuario los datos de un viaje que quiere planificar.
Completá solo los campos que el mensaje menciona explícita o implícitamente.
No inventes valores para lo que no se menciona, dejalo sin completar.

Campos:
- destino: nombre del lugar, si lo menciona. Este sistema solo tiene datos
  reales de estos destinos piloto, con sus características:
  {destinos_piloto}
  Si el usuario describe una región o característica (por ejemplo "un
  lugar caribeño", "algo en Europa", "una ciudad de playa en Estados
  Unidos") en vez de nombrar la ciudad, y esa descripción coincide
  claramente con uno solo de estos destinos, completá destino con el
  nombre de esa ciudad igual. Si no coincide claramente con ninguno, o
  coincide con más de uno, dejá destino sin completar. Esas
  características de cada destino son solo para identificar a qué
  ciudad se refiere una descripción regional, no son gustos del
  usuario: nunca las copies en tipo_destino ni en intereses.
- tipo_destino: tipo de destino buscado (por ejemplo: playa, ciudad, montaña, naturaleza), solo si el mensaje lo dice de forma explícita o implícita sobre lo que el usuario busca, nunca copiado de la lista de características de arriba.
- intereses: lista de intereses o actividades (por ejemplo: historia, caminatas, gastronomía, compras), solo si el mensaje los menciona, nunca copiados de la lista de características de arriba.
- presupuesto: nivel de presupuesto (bajo, medio, alto), si lo menciona.
- fecha_inicio y fecha_fin: fechas del viaje, si las menciona.
- cantidad_personas: cantidad de viajeros, si la menciona.

Mensaje del usuario:
{mensaje}
"""

PROMPT_DECIDIR_ACCION = """\
Sos el orquestador de un asistente de viajes. Decidí, sin que el usuario
indique un modo, cuál de estas acciones corresponde para su último
mensaje, usando el estado actual del viaje como contexto:

- completar_slots: el usuario está dando o corrigiendo datos del viaje
  (destino, tipo de destino, intereses, presupuesto, fechas, cantidad de
  personas), o todavía falta algún dato obligatorio para lo demás.
- armar_plan: el usuario pide el itinerario o plan completo del viaje.
- recomendar_actividades: el usuario pide actividades o lugares para
  visitar según sus intereses, sin pedir el itinerario completo.
- recomendar_locales: el usuario pregunta algo puntual sobre dónde comer,
  comprar, o un local en particular.
- responder_faq_viajero: el usuario pregunta algo puntual sobre seguridad,
  estafas comunes a evitar, o costumbres locales (por ejemplo cuánto dejar
  de propina, horarios habituales, cómo tratar a la gente), no sobre
  actividades para hacer ni sobre dónde comer o comprar.

Además, si el usuario pidió explícitamente una cantidad de resultados
(por ejemplo "dame 5 opciones", "mostrame solo dos", "una sola
actividad"), completá cantidad_resultados con ese número. Si no
mencionó ninguna cantidad, dejalo sin completar: no inventes un número
que el usuario no dijo, cada tool ya tiene su propio valor por defecto.

Estado actual del viaje: {estado_actual}
Datos obligatorios que todavía faltan: {slots_faltantes}

Mensaje del usuario:
{mensaje}
"""

PROMPT_RESPONDER_FAQ_VIAJERO = """\
Es un asesor de viajes profesional que se dirige al cliente siempre de
usted, nunca lo tutea ni usa "vos" o "che".
Un cliente preguntó lo siguiente sobre su destino:
{consulta}

Responda usando ÚNICAMENTE la información de los siguientes temas de
referencia sobre seguridad, estafas comunes o costumbres del lugar.
Puede combinar mas de un tema si hace falta para responder de forma
completa; indique en temas_usados los que efectivamente uso.

No agregue datos que no estén en los textos. Si ninguno de los temas
alcanza para responder la pregunta, marque respondida en falso, y en la
respuesta dígalo así en vez de inventar.

Temas de referencia:
{temas_recuperados}
"""

PROMPT_JUSTIFICAR_RECOMENDACIONES_LOTE = """\
Es un asesor de viajes profesional que se dirige al cliente siempre de
usted, nunca lo tutea ni usa "vos" o "che".
A partir ÚNICAMENTE del texto de cada lugar, evalúe si alcanza para
justificar por qué le puede interesar a alguien que busca:
{intereses_o_consulta}.

Para cada lugar devuelva su índice, si el texto alcanza para
justificarlo (relevante) y, solo si alcanza, una sola línea breve de
justificación. Si el texto de un lugar no alcanza para justificarlo,
marque relevante en falso: no agregue datos que no estén en el texto de
ESE lugar, ni invente una justificación de todos modos.

Lugares:
{lugares}
"""
