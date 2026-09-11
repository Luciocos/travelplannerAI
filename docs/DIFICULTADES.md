# Dificultades encontradas

"Identificación de dificultades" es un criterio de evaluación con peso propio, y es el punto 6 de los contenidos mínimos del video. Anotar cada problema real en el momento en que aparece. Un TP que no puede contar ningún problema pierde puntos en ese criterio.

Formato de cada entrada:

## P-NN, título del problema

- **Fecha:** 
- **Fase:** 
- **Síntoma:** qué se vio, con el error concreto si lo hubo.
- **Causa:** qué lo estaba produciendo.
- **Solución:** qué se hizo.
- **Aprendizaje:** qué cambia de acá en adelante por esto.

---

## P-01, destinos piloto del handoff no son coordenadas utilizables

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Síntoma:** el handoff inicial define los destinos piloto como "Europa, Miami, Caribe". Al escribir el cliente de OpenTripMap se vio que la búsqueda por radio necesita una coordenada puntual, no sirve un continente ni una región.
- **Causa:** el handoff se escribió pensando en el caso de negocio (tipos de viaje que el sistema cubre) y no en el requisito técnico de la fuente de datos.
- **Solución:** el pipeline de ingesta (`ingerir_destino`, `scripts/ingestar_destino.py`) se dejó parametrizado por destino + `lat`/`lon`, listo para correr apenas el equipo defina ciudades concretas. No se inventó una ciudad por decisión unilateral, ver D-04 en `DECISIONES.md`.
- **Aprendizaje:** un destino piloto para este sistema tiene que ser una ciudad o localidad puntual, no una región. Repasar esto en la defensa como parte de las decisiones de alcance.

---

## P-02, corpus de comercios (y de atractivos en Cancún) por debajo del mínimo con solo la API

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Síntoma:** al correr `scripts/ingestar_destino.py` contra los tres destinos piloto: Barcelona 41 atractivos / **2 comercios**, Miami 75 atractivos / **2 comercios**, Cancún **7 atractivos** / **0 comercios** (mínimo pedido: 25 y 15 respectivamente). Se probó relajar el filtro de significancia (`rate=1`) y ampliar el radio a 50km para Cancún: subió de 0 a 7 atractivos, comercios siguió en 0.
- **Causa:** la mayoría de los POIs de `foods`/`shops`/`marketplaces` en OpenTripMap no tienen extracto de Wikipedia (fuente del texto que se embebe), independientemente de la ciudad. En Cancún además hay poca densidad de contenido editorial también para atractivos, incluso en un radio de 50km.
- **Solución:** se aceptó el número real de la API como está, sin seguir ajustando parámetros (decisión explícita del usuario, para no perder tiempo de desarrollo persiguiendo un dato que la fuente no tiene). El faltante se completa con curaduría manual en `data/curated/`, marcado `fuente='curado'`, como prevé la skill del proyecto para este caso exacto.
- **Aprendizaje:** para este tipo de fuente (POIs geográficos con texto opcional de Wikipedia), el corpus de comercios va a depender de curaduría manual en cualquier destino, no es un problema de parámetros de búsqueda. Dimensionar el tiempo de curaduría en el cronograma en función de esto, no como una tarea chica de "completar lo que falte".

## P-03, Amadeus for Developers discontinuado, migración a RapidAPI

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta Fase 7)
- **Síntoma:** al ir a generar las credenciales de Amadeus documentadas para RF6/RF7, el registro self-service ya no existía.
- **Causa:** Amadeus decidió discontinuar el portal self-service de su API (pausa de altas nuevas desde marzo/abril de 2026, decomisionado por completo el 2026-07-17), sin relación con nada del proyecto.
- **Solución:** migración completa a RapidAPI (Booking.com15 + Fly Scraper), documentada en `migracion-amadeus-a-rapidapi.md` y D-05/D-06 de este documento. Antes de escribir los adaptadores se verificó cada endpoint con llamadas reales, lo que reveló que Fly Scraper tampoco funciona como se esperaba (ver P-04).
- **Aprendizaje:** una decisión de arquitectura basada en "API self-service gratuita de un tercero" puede quedar invalidada por una decisión de negocio del proveedor, sin aviso. Vale la pena, para la defensa, tener el argumento de por qué el diseño (tools con firma estable, adaptador único por debajo) permitió absorber el cambio sin tocar el resto del sistema.

## P-04, la mayoría de los endpoints anunciados de Fly Scraper no funcionan

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta Fase 7)
- **Síntoma:** `auto-complete`, `search-oneway`, `search-roundtrip`, `get-airports`, `search-everywhere` (probados en variantes singular/plural, con y sin prefijo `v2`) devuelven `404` con el mensaje `"Endpoint '...' does not exist"`, directo del proxy de RapidAPI (header `X-RapidAPI-Proxy-Response: true`, nunca llegan al backend real), a pesar de estar listados en el Playground de la API con esos nombres exactos.
- **Causa:** desconocida (no es un problema de suscripción ni de la key, confirmado con otro endpoint de la misma API que sí responde). Aparentemente el Playground anuncia rutas que no están realmente registradas en el backend de este proveedor.
- **Solución:** se descartó Fly Scraper como fuente de búsqueda de vuelos. El único endpoint que responde con datos reales, `v2/flights/price-calendar`, se usa solo como dato complementario. Booking.com15 quedó como fuente única de RF6 y RF7 (D-06).
- **Aprendizaje:** con wrappers no oficiales o de terceros en marketplaces como RapidAPI, la documentación del Playground no es garantía de que el endpoint funcione. Verificar cada endpoint con una llamada real antes de comprometer una arquitectura a él, que es justo lo que pedía el documento de migración y lo que permitió detectar esto a tiempo.

---

## P-05, matching de destino sensible a tildes rompía la recuperación

- **Fecha:** 2026-09-11
- **Fase:** 5 (Fase 3/RAG en general)
- **Síntoma:** al probar el orquestador a mano (`scripts/chat.py`), un destino escrito con tilde por el usuario ("Cancún") no encontraba nada si el dato ingerido estaba sin tilde ("Cancun", como lo carga `scripts/ingestar_destino.py`), o viceversa según cómo el LLM extrajera el nombre.
- **Causa:** la consulta canónica (`recuperacion/_consulta.py`) filtraba por `destino = %(destino)s`, comparación de igualdad exacta de string, sensible a tildes y mayúsculas. El lookup de coordenadas por destino en `agente.py` (`data/reference/destinos.json`) tenía el mismo problema, como dict exacto.
- **Solución:** extensión `unaccent` de Postgres (agregada al esquema) más `lower()` en la consulta canónica; y una normalización equivalente en Python (`unicodedata`, sin librerías nuevas) para el lookup de `destinos.json`. Verificado contra la base real: "Cancún" y "Cancun" devuelven exactamente los mismos resultados.
- **Aprendizaje:** cualquier comparación de texto libre generado por un LLM (nombres de destino, ciudades) tiene que asumir variación de tildes/mayúsculas por defecto, no como caso raro. Vale revisar si hay otro punto de comparación de texto libre en el sistema con el mismo riesgo.

## P-06, latencia real de Gemini se degrada con uso acumulado (sin resolver)

- **Fecha:** 2026-09-11
- **Fase:** 5, pero afecta a cualquier tool que use el LLM
- **Síntoma:** al probar la conversación completa a mano, cada turno tardaba mucho más de lo esperado. Una sola invocación aislada (`rotador.invocar`, sin tools ni contexto extra) tardó **42 segundos**, contra 1-3 segundos en las primeras pruebas de la sesión con el mismo modelo y las mismas claves.
- **Causa (probable, no confirmada):** cuota por minuto (RPM) de Gemini rozándose por el volumen de llamadas reales hechas en la sesión (decenas, entre verificar cada fase y la conversación de prueba). No hay error duro en los logs (`RotadorClavesGemini` no registró ningún backoff ni clave agotada), así que no es el mecanismo de reintento del propio rotador el que agrega la demora: la lentitud viene de la respuesta de la API en sí.
- **Solución:** ninguna aplicada todavía. No se puede confirmar la causa exacta sin entrar logueado a `aistudio.google.com/rate-limit` (mismo bloqueo abierto de `estado.md` sobre el límite diario/por minuto real). Mitigación de código pendiente de evaluar: reducir la cantidad de llamadas al LLM por turno (por ejemplo, `recomendar_actividades`/`recomendar_locales` hacen una llamada de justificación por resultado, podrían batchearse en una sola).
- **Aprendizaje:** un modelo "Flash Lite" gratuito no garantiza latencia baja sostenida bajo uso intensivo de desarrollo/testing; hay que probar el sistema en vivo con volumen real antes de la demo, no asumir que el tiempo de respuesta de las primeras pruebas se mantiene. Para el video/demo, conviene espaciar las pruebas o tener un colchón de tiempo por si la cuota está ajustada ese día.
- **Addendum 2026-09-11, GUI (Fase 7B):** al probar la GUI de Streamlit, el usuario reportó un turno de `completar_slots` con destino inferido de una región (ej. "7 días a Europa") que tarda especialmente: ese turno dispara **3 llamadas secuenciales** a Gemini (`_decidir_accion` del orquestador, extracción de slots, generación de la pregunta), cada una potencialmente afectada por la degradación de arriba. Mitigación aplicada: la GUI ahora muestra un spinner ("Pensando...") mientras espera, así al menos queda claro que el sistema está trabajando y no colgado (antes no había ningún indicador). Mitigación de fondo (fusionar llamadas) sigue pendiente de evaluar, no aplicada, ver D-10 en `DECISIONES.md` sobre por qué no se fusionó `_decidir_accion` con la extracción.

## P-07, el LLM de extracción copiaba las características del destino inferido como gustos del usuario

- **Fecha:** 2026-09-11
- **Fase:** 4 (RF1/RF2, `completar_slots`), regresión introducida por D-09
- **Síntoma:** al verificar la GUI con el mensaje real "quiero ir de viaje 7 dias a europa?", el sistema infirió correctamente `destino=Barcelona`, pero también completó `tipo_destino="ciudad"` e `intereses=["historia", "arquitectura", "cultura"]` — datos que el usuario nunca mencionó. Coincidían exactamente con la lista `caracteristicas` de Barcelona en `destinos.json`.
- **Causa:** `PROMPT_EXTRAER_SLOTS` (D-09) le pasa al LLM las características de cada destino piloto para que pueda mapear una descripción regional ("un lugar en Europa") al destino correcto, pero no aclaraba que esa lista es solo para identificar la ciudad, no una fuente de gustos del usuario. El LLM la reutilizó también para completar `tipo_destino`/`intereses`, violando la restricción dura 5 ("nada inventado").
- **Solución:** se agregó una aclaración explícita en el prompt: las características de cada destino son solo para identificar la ciudad, nunca se copian a `tipo_destino` ni a `intereses`; esos dos campos solo se completan con lo que el mensaje dice explícita o implícitamente. Verificado de nuevo con el LLM real contra el mismo mensaje: `tipo_destino` e `intereses` quedaron `None`. Test de regresión agregado (`test_prompt_extraccion_aclara_que_caracteristicas_no_son_gustos_del_usuario` en `test_completar_slots.py`), aunque por ser comportamiento de LLM solo verifica que la instrucción está en el prompt, no que el modelo la respete siempre.
- **Aprendizaje:** darle al LLM contexto de referencia para una tarea (acá, características para *matchear* destino) puede filtrarse a otros campos de la misma llamada de extracción si no se acota explícitamente el uso de ese contexto. Cada dato de contexto agregado a un prompt de extracción estructurada necesita decir para qué sirve y para qué no.

## Candidatos previsibles, confirmar si pasan de verdad

No inventar entradas. Estos son los puntos donde es probable que algo falle, listados para que se registren bien si ocurren:

- Cuota o caída de la API de OpenTripMap durante el desarrollo.
- Extractos de Wikipedia en inglés mezclados con consultas en español, y el efecto en la recuperación.
- El agente eligiendo la tool equivocada por un docstring ambiguo.
- Slot filling que repregunta algo ya respondido, o que pisa un slot cargado con None.
- Open-Meteo sin pronóstico para fechas a más de 16 días.
