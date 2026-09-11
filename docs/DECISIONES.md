# Decisiones técnicas

Una entrada por decisión. Este documento es el insumo directo de la defensa oral y del punto 4 del video ("justificación de las decisiones tomadas"). Se escribe en el momento de decidir, no al final reconstruyendo de memoria.

Formato de cada entrada:

## D-NN, título de la decisión

- **Fecha:** 
- **Fase:** 
- **Contexto:** qué problema había que resolver.
- **Decisión:** qué se eligió.
- **Alternativas descartadas:** qué más se evaluó y por qué no.
- **Consecuencias:** qué se gana, qué se pierde, qué queda condicionado a esto.

---

## D-01, PostgreSQL con pgvector como vector store

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** el sistema necesita un vector store para tres corpus de RAG, con filtrado previo por destino.
- **Decisión:** PostgreSQL con la extensión pgvector.
- **Alternativas descartadas:** Chroma. Descartada por pedido explícito del profesor, y porque obliga a resolver el filtro por metadata y la búsqueda semántica en dos pasos separados.
- **Consecuencias:** el filtro por destino y la búsqueda por similitud se resuelven en una sola consulta SQL. Las tablas estructuradas (itinerarios, gastos) viven en la misma base que los vectores, un solo motor en vez de dos. Costo, hay que administrar una base de datos.

## D-02, Postgres gestionado en Supabase en vez de solo Docker local

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** se necesita una base Postgres con pgvector accesible por todo el equipo, no solo en la maquina de quien programa.
- **Decisión:** Supabase (Postgres 16 con pgvector) como base compartida, vía `DATABASE_URL`. `docker-compose.yml` queda como alternativa para desarrollo 100% local o para el CI.
- **Alternativas descartadas:** solo Docker local, descartado porque cada integrante tendría datos distintos y el trabajo en equipo se complica. Neon, no elegido por preferencia del equipo por Supabase.
- **Consecuencias:** todos apuntan a la misma base durante el desarrollo. Hay que evitar correr la ingesta completa en paralelo sin coordinarse, para no pisarse datos. La connection string va solo en `.env`, nunca en el repo.

## D-03, Modelo Gemini: `gemini-3.5-flash-lite`, confirmado contra la API real

- **Fecha:** 2026-09-10
- **Fase:** 0
- **Contexto:** el plan pide verificar contra la documentación oficial de Google cuál es el Flash-Lite vigente y su límite diario antes de cerrar la Fase 0. Una revisión de la documentación (`ai.google.dev`) no alcanzó a confirmar el dato limpio (ver primera versión de esta decisión). Al correr `smoke_llm.py` por primera vez contra las 5 claves reales, `gemini-2.5-flash-lite` devolvió `404 NOT_FOUND`: `"This model models/gemini-2.5-flash-lite is no longer available to new users. Please update your code to use models/gemini-3.5-flash-lite"`.
- **Decisión:** `GEMINI_MODEL=gemini-3.5-flash-lite`, confirmado con `smoke_llm.py` real (5/5 claves responden `200 OK`). Actualizado en `.env`, `.env.example` y los cuatro workflows de `.github/workflows/` y `assets/workflows/`.
- **Alternativas descartadas:** `gemini-2.5-flash-lite`, que seguía figurando como estable en la documentación pública pero ya no está disponible para las cuentas nuevas de este equipo. La documentación de terceros y la propia doc de Google resultaron menos confiables que el error real de la API para esta decisión.
- **Consecuencias:** el límite diario real por clave del tier gratuito sigue sin confirmar (ver bloqueo en `estado.md`, la página de rate limits de Google ya no publica un número fijo). El ID de modelo ya no es bloqueo.

## D-04, Destinos piloto "Europa" y "Caribe" resueltos a ciudades puntuales

- **Fecha:** 2026-09-10
- **Fase:** 1
- **Contexto:** el handoff fija como destinos piloto "Europa, Miami, Caribe". OpenTripMap busca por radio alrededor de una coordenada puntual (`lat`/`lon` + radio en metros), no acepta un continente ni una región como unidad de búsqueda. Miami es una ciudad y funciona sin cambios; "Europa" y "Caribe" no.
- **Decisión:** "Europa" se resuelve a **Barcelona**. "Caribe" se resuelve a **Cancún / Riviera Maya**, México. Ambas confirmadas por el usuario tras propuesta de opciones.
- **Alternativas descartadas para Europa:** París (riesgo de sobrecarga de resultados en OpenTripMap, exige filtrado más agresivo), Roma (buena en histórico/patrimonio pero más floja en gastronomía/comercios curados que Barcelona).
- **Alternativas descartadas para Caribe:** Punta Cana, República Dominicana (destino caribeño "correcto" geográficamente, pero se prefirió Cancún/Riviera Maya); San Juan, Puerto Rico (buena mezcla histórico/playas pero menor volumen de POIs que las otras dos opciones).
- **Consecuencias:** Cancún/Riviera Maya está en el Golfo de México, no en el mar Caribe en sentido estricto; queda anotado para poder explicarlo en la defensa si se pregunta por qué "Caribe" resuelve a ese punto. Con las coordenadas ya decididas, se puede correr `python -m scripts.ingestar_destino --destino <nombre> --lat <lat> --lon <lon>` para Barcelona y Cancún en cuanto esté cargada `OPENTRIPMAP_API_KEY`.

## D-05, Amadeus for Developers self-service dado de baja, RF6/RF7 sin fuente vigente

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta planificación de Fase 7)
- **Contexto:** `fuentes-datos.md` documentaba Amadeus for Developers, entorno de test self-service, como la fuente para RF6 (alojamiento) y RF7 (vuelos), justamente por no requerir aprobación de partner (a diferencia de Booking). Al ir a buscar cómo conseguir las credenciales, se encontró que Amadeus decidió discontinuar ese portal.
- **Decisión:** no se buscó ni se adoptó un reemplazo unilateralmente. Se marcó la sección de Amadeus en `fuentes-datos.md` como dada de baja y se dejó como bloqueo abierto en `estado.md`, a resolver por el equipo antes de llegar a Fase 7.
- **Alternativas descartadas:** ninguna evaluada todavía a propósito, para no decidir el reemplazo sin el equipo. Opciones a evaluar cuando se retome: otra API self-service de vuelos/hoteles gratuita, o directamente cortar RF6/RF7 de las extensiones (ya son las de menor prioridad en el orden de `plan-de-fases.md` Fase 7, después de RF8).
- **Consecuencias:** no afecta el núcleo (Fases 0-6, RF1-5/RF11/RF12), que no depende de Amadeus. Sí afecta cuánto se puede prometer de extensiones si no se encuentra reemplazo a tiempo. Evidencia del hallazgo: registro de usuarios nuevos pausado desde marzo/abril de 2026, portal decomisionado el 2026-07-17, keys existentes desactivadas desde esa fecha (confirmado por cobertura de prensa especializada, no por documentación propia de Amadeus verificada en el momento).

## D-06, RF6/RF7 migrados a RapidAPI (Booking.com15), Fly Scraper reducido a dato complementario

- **Fecha:** 2026-09-10
- **Fase:** 0 (afecta planificación de Fase 7)
- **Contexto:** resuelto el bloqueo de D-05. El plan de migración (`migracion-amadeus-a-rapidapi.md`) proponía Fly Scraper como fuente primaria de vuelos y Booking.com15 (vía RapidAPI) como fuente primaria de hoteles, con fallback cruzado entre ambas. Antes de escribir los parsers se verificó cada endpoint con llamadas reales, como pide el documento.
- **Decisión:** Booking.com15 es la fuente única y real para RF6 **y** RF7 (`api/v1/hotels/searchDestination` → `searchHotels`; `api/v1/flights/searchDestination` → `searchFlights`, esta última con nombre de endpoint verificado por prueba y error, no es `searchFlightLocation` como sugeriría el playground). Fly Scraper queda reducido a un solo endpoint que sí funciona (`v2/flights/price-calendar`, acepta código IATA directo), usado como dato complementario opcional, nunca como fuente de `buscar_vuelos`. Implementado en `src/asistente_viajes/services/rapidapi/` con cache de resolución de destino en Postgres (`destino_externo`), guard de cuota persistido (`uso_api_mensual`), fixtures con respuestas reales, y fallback a fixture marcado (`es_fixture=True`) si la API falla.
- **Alternativas descartadas:** fallback cruzado real entre Booking.com15 y Fly Scraper para vuelos, como proponía el documento original — descartado porque de los cinco endpoints de búsqueda de Fly Scraper probados (`auto-complete`, `search-oneway`, `search-roundtrip`, `get-airports`, `search-everywhere`, en variantes singular/plural y con/sin `v2`), **ninguno respondió con datos reales**: todos dan 404 directo del proxy de RapidAPI (confirmado con el header `X-RapidAPI-Proxy-Response: true`, nunca llegan al backend), a pesar de estar listados en el playground de la API.
- **Consecuencias:** sin fallback cruzado real, si Booking.com15 falla (cuota agotada, caída) la tool cae directo a un fixture marcado como dato de ejemplo, no a otro proveedor. La tabla `destino_externo` distingue dominio con `proveedor = 'booking_hoteles' | 'booking_vuelos'` porque comparten host pero no namespace de id. `search_type`/`type` de Booking.com15 vienen en minúscula para hoteles y mayúscula para vuelos — un detalle que la documentación de terceros no deja claro y que rompe la búsqueda si se asume mal.

## D-07, RF4 (recomendación de comercios) movido de núcleo a extensión

- **Fecha:** 2026-09-10
- **Fase:** 1 (afecta el "Mapa de requerimientos" y el orden de núcleo/extensiones de la skill)
- **Contexto:** al correr la ingesta real de OpenTripMap contra los tres destinos piloto, el corpus de comercios quedó muy por debajo del mínimo pedido (15 por destino) en los tres casos: Barcelona 2, Miami 2, Cancún 0. La causa no es un parámetro de búsqueda mal puesto (se probó relajar `rate` y ampliar el radio para Cancún, sin mejora en comercios): la mayoría de los POIs de `foods`/`shops`/`marketplaces` en OpenTripMap directamente no tienen extracto de Wikipedia. Cerrar esto por API sola no es viable; cerrarlo por curaduría manual exigiría 8 o más horas de trabajo del equipo repartidas entre los tres destinos.
- **Decisión:** se scopea el núcleo del proyecto a **un solo RAG robusto y testeado: atractivos turísticos** (RF3, `recomendar_actividades`). RF4 (`recomendar_locales`) se mueve de la tabla de núcleo a la de extensiones en `SKILL.md`, y el mínimo de 15 comercios deja de ser criterio de aceptación de Fase 1. El código de RF4 (tool, retriever, tests con mocks) no se borra, queda escrito y listo para activarse cuando haya un corpus real.
- **Alternativas descartadas:** (a) invertir 8+ horas de curaduría manual de comercios en los tres destinos ahora, descartado por no ser el uso más valioso del tiempo disponible antes de la entrega; (b) seguir ajustando parámetros de la búsqueda por radio de OpenTripMap, descartado porque ya se probó y el problema es de disponibilidad de datos en la fuente, no de parámetros (ver P-02 en `DIFICULTADES.md`).
- **Consecuencias:** el proyecto pasa de "tres RAGs" a "un RAG núcleo (atractivos) + dos RAGs de extensión (comercios, FAQ)". Si el tiempo lo permite antes de la entrega, RF4 se retoma con **Yelp API** (mencionada por el equipo como alternativa a evaluar) o con curaduría manual dedicada. Actualizado en `SKILL.md` (reglas, mapa de requerimientos, "Los RAGs") y `plan-de-fases.md` (Fase 1, 3 y 7).
- **Addendum 2026-09-10:** el mínimo de atractivos por destino de Fase 1 también se bajó de 25 a 20, por el mismo motivo de fondo (baja densidad de contenido editorial de OpenTripMap en Cancún, incluso ampliando radio a 50km y relajando el filtro `rate`). Reduce de ~18 a ~13 los atractivos curados a mano que hacen falta para Cancún.

## D-08, orquestador (Fase 5) implementado como decisión de LLM, no como agente de tools ni LangGraph

- **Fecha:** 2026-09-11
- **Fase:** 5
- **Contexto:** `arquitectura.md` proponía un "agente de LangChain con memoria de sesión" para decidir entre los tres caminos de RF12, con migración a LangGraph si el flujo se complicaba. Al escribir `agente.py`, había dos formas razonables de implementar "el LLM decide sin bind_tools/ReAct": una decisión de clasificación con salida estructurada (mismo patrón que `completar_slots`, que ya existía y estaba probado) o un agente de tools con `bind_tools` y un loop de ejecución de herramientas.
- **Decisión:** se implementó como una decisión de clasificación con salida estructurada (`DecisionAccion`, un enum de 4 acciones) sobre el mensaje y el estado actual, reutilizando el mismo patrón y la misma infraestructura de rotación de claves (`RotadorClavesGemini.con_salida_estructurada`) que ya usaba `completar_slots`. `info_destino` queda fuera de esa decisión a propósito (RF12, única excepción): se dispara aparte, determinísticamente, la primera vez que destino y fechas quedan confirmados en la sesión.
- **Alternativas descartadas:** agente de tools de LangChain con `bind_tools` y loop de ejecución (mas cercano al patrón "ReAct" clásico) — descartado por ahora porque agrega una capa de ejecución y parseo de tool calls que no aporta sobre la clasificación estructurada para solo 4 acciones fijas, y porque la rotación de claves ya funciona sobre `con_salida_estructurada`, no sobre `bind_tools`. LangGraph, descartado por lo mismo: el flujo (RF12) no mostró necesidad de nodos explícitos todavía. Ambos quedan como camino de migración documentado en `arquitectura.md` si el flujo crece.
- **Consecuencias:** verificado con una conversación real de 6 turnos (LLM, corpus y Postgres reales): el orquestador eligió la tool correcta en cada turno sin que el mensaje del usuario indicara nunca un modo (RF12), y el estado se mantuvo sin pérdidas entre turnos (RF11). `SesionAgente` vive en memoria del proceso, no se persiste entre sesiones (fuera de alcance del núcleo).

## D-09, matching de destino insensible a tildes y descripciones regionales interpretadas contra los destinos piloto

- **Fecha:** 2026-09-11
- **Fase:** 4 (RF1/RF2, `completar_slots`)
- **Contexto:** dos problemas de comprensión de lenguaje natural en la práctica. Primero, `_coordenadas_destino` (agente.py) y `buscar_destino_cacheado` (cache de RapidAPI) normalizaban tildes/mayúsculas cada uno con su propia copia de la misma función, duplicada en tres lugares. Segundo, un usuario que pide "un lugar caribeño" o "algo en Europa" sin nombrar la ciudad no cargaba el slot `destino`, aunque el sistema solo tiene tres destinos piloto y la región alcanza para identificar uno solo (D-04: "Caribe" ya se había resuelto a Cancún/Riviera Maya a nivel de decisión de producto, pero `completar_slots` no lo aplicaba en runtime).
- **Decisión:** (1) se extrajo la normalización de texto (`unicodedata`, NFKD, lower, trim) a un único módulo compartido, `asistente_viajes/texto.py` (`normalizar`), y un módulo `asistente_viajes/destinos.py` con la lectura única de `data/reference/destinos.json` (`cargar_destinos_piloto`, `buscar_destino_piloto`), consumidos por `agente.py` y `cache.py` en vez de cada uno reimplementar lo mismo. (2) se agregó una lista de `caracteristicas` por destino piloto en `destinos.json`, inyectada en `PROMPT_EXTRAER_SLOTS` para que el LLM de extracción de slots pueda mapear una descripción regional a un destino piloto cuando coincide con uno solo, y se dejó explícito en el prompt que si no coincide claramente o coincide con más de uno, el slot queda sin completar. Cuando el destino se infiere así (no aparece literal en el mensaje del usuario), la pregunta del turno lo confirma explícitamente ("¿te referís a Cancún?") en vez de asumirlo en silencio, para no violar la regla de "nada inventado" (restricción dura 5 de la skill).
- **Alternativas descartadas:** mapeo regex/diccionario fijo de regiones a ciudades (ej. `{"caribe": "Cancun", "europa": "Barcelona"}`), descartado porque es frágil ante variaciones de lenguaje natural ("una isla del Caribe", "algo caribeño") y porque el LLM de extracción ya corre en ese punto del flujo, así que darle las características como contexto no agrega una llamada nueva.
- **Consecuencias:** `completar_slots` interpreta descripciones regionales sin inventar datos (siempre confirma), y queda un solo punto de verdad para normalización de texto y lectura de `destinos.json`. Cubierto por tests unitarios mockeados (`test_texto.py`, `test_destinos.py`, casos nuevos en `test_completar_slots.py` y `test_agente.py`).

## D-10, el orquestador tambien elige cantidad_resultados, no solo la tool (redefine D-08)

- **Fecha:** 2026-09-11
- **Fase:** 5 (redefine el alcance original de D-08, no lo reemplaza)
- **Contexto:** se discutió si convenía que el orquestador, además de elegir la tool, también generara los parámetros de la llamada (patrón estándar de function-calling: el LLM rutea y arma argumentos, la tool hace el trabajo real). El riesgo identificado: para parámetros que ya son estado validado (`destino`, `intereses`, fechas, `cantidad_personas`), pedírselos de nuevo al LLM leyendo solo el mensaje del turno actual no suma nada (el dato ya está garantizado por el merge no destructivo de RF2 en `sesion.estado`) y sí puede perder algo (transcripción o hallucination, más probable con un modelo chico como Flash Lite). En cambio, había un parámetro de refinamiento real que hoy estaba hardcodeado sin necesidad: `k` (cantidad de resultados) estaba fijo en 3 en `procesar_mensaje` para `recomendar_actividades`/`recomendar_locales`, ignorando si el usuario pedía explícitamente "dame 5 opciones" o "solo una".
- **Decisión:** se separan los parámetros en dos categorías. Los que ya son estado validado siguen inyectándose siempre desde `sesion.estado` en el wrapper de Python, nunca se los pide el LLM. Los de refinamiento sí se agregan al schema de decisión: `DecisionAccion` gana `cantidad_resultados: int | None`, extraído por el mismo LLM y el mismo prompt que ya decidía la acción (`PROMPT_DECIDIR_ACCION`), sin tocar `RotadorClavesGemini` ni migrar a `bind_tools`. Si el usuario no menciona una cantidad, el campo queda `None` y cada tool usa `CANTIDAD_RESULTADOS_DEFECTO` (3, el mismo valor que estaba hardcodeado).
- **Alternativas descartadas:** migrar a `bind_tools()` real de LangChain con un loop de ejecución de tool calls, para que el LLM arme todos los parámetros de cada tool (incluidos destino/intereses/fechas) — descartado por el riesgo de arriba y porque agrega trabajo de infraestructura no trivial (el rotador de claves con failover por 429 solo soporta hoy `.invocar()`/`.con_salida_estructurada()`, no `bind_tools()`). Dejar `k` hardcodeado tal como estaba — descartado porque es exactamente el caso donde el usuario sí da una señal explícita en lenguaje natural que el sistema estaba ignorando.
- **Consecuencias:** verificado con LLM y Postgres reales, conversación de 3 turnos: "dame 5 actividades para hacer" produjo `recomendar_actividades` con `cantidad_resultados=5`, "dame solo 1 opción de dónde comer barato" produjo `recomendar_locales` con `cantidad_resultados=1`, y el estado (destino, intereses, fechas, cantidad de personas) se mantuvo intacto en las 3 vueltas sin que el LLM tuviera que reconstruirlo. `_decidir_accion` ahora devuelve el objeto `DecisionAccion` completo (antes devolvía solo el string de la acción); los tests de `test_agente.py` se actualizaron en consecuencia.
