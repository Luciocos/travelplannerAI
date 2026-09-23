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

## D-11, RF10 (gastos del viaje) omitido, no se implementa

- **Fecha:** 2026-09-11
- **Fase:** 7 (extensiones)
- **Contexto:** con el núcleo cerrado y RF9 (FAQ del viajero) ya implementado, quedaban por priorizar las extensiones restantes de Fase 7: RF10 (gastos y división) y retomar RF4 (comercios) si quedaba tiempo. `plan-de-fases.md` ya marcaba a RF10 como la extensión de menor valor diferencial en términos de IA ("es lógica de producto, no de IA, salvo que se le sume parseo NLP... que sí suma y es barato").
- **Decisión:** el usuario decidió omitir RF10 directamente del alcance del TP, no implementarlo ni dejarlo escrito a medias. `registrar_gasto`/`calcular_division_gastos` no se agregan al código ni a las tools del agente.
- **Alternativas descartadas:** implementarlo como lógica de producto simple (tablas `gasto`/`participante` + algoritmo de minimización de transferencias, sin IA) tal como preveía `plan-de-fases.md` — no elegido, decisión directa del usuario de priorizar el tiempo restante en otra cosa (documentación, notebook de demo, cierre de infraestructura).
- **Consecuencias:** `SKILL.md` (mapa de requerimientos) y `plan-de-fases.md` (Fase 7) quedan actualizados marcando RF10 como omitido. El esquema SQL no necesita las tablas `gasto`/`participante` que preveía `arquitectura.md`; no hay código ni tests de RF10 en el repo.

## D-12, orquestador migrado a LangGraph (redefine D-08)

- **Fecha:** 2026-09-17
- **Fase:** 7C (fine-tuning post-núcleo)
- **Contexto:** probando el sistema en una conversación real y libre (no los casos de prueba guionados de las fases anteriores) aparecieron límites de fondo del diseño de D-08: una decisión de clasificación de UNA tool por turno, mirando solo el mensaje del turno actual. No podía atender más de un pedido en el mismo mensaje ("armame el plan y decime dónde comer"), y no tenía forma de responder algo que ya sabía (recordar el destino elegido, agradecer un "gracias") porque no había memoria de conversación más allá de `PreferenciasViaje`. `arquitectura.md` ya prevía esta migración ("si el flujo se vuelve difícil de controlar, migrar a LangGraph con nodos explícitos").
- **Decisión:** se migra a un grafo de LangGraph (`grafo.py`) con nodos de responsabilidad única: `interpretar` (un llamado estructurado que extrae los datos del viaje Y decide qué acciones pidió el cliente, puede ser más de una) → `actualizar_estado` (parseo y merge determinístico, nunca el LLM) → `planificar` (decide qué ejecutar: pregunta consolidada si falta algo, más una recomendación de regalo; re-arma el plan solo si un dato relevante cambió) → `ejecutar_acciones` (un nodo con un loop de Python que llama a cada tool, cada una con su propio try/except) → `disparar_info_destino` (única excepción a que decida el LLM, RF12) → `redactar` (solo llama al LLM si no se ejecutó ninguna acción: recap, small talk, fuera de alcance). Las dependencias (conexión, rotador, fecha de hoy) se inyectan por runtime context de LangGraph (`context_schema`), no por `config["configurable"]`.
- **Alternativas descartadas:** un nodo de grafo por tool (patrón hub-and-spoke con aristas condicionales de vuelta al hub) — descartado por tiempo: un solo nodo `ejecutar_acciones` con un loop interno da el mismo resultado observable y es mucho menos código, a costa de que el grafo no muestre cada tool como nodo separado en `draw_mermaid()`. Mantener D-08 (clasificación de una sola acción) y resolver el multi-intent con post-procesamiento de texto — descartado porque no resuelve la memoria de conversación, que era el problema de fondo.
- **Consecuencias:** verificado con LLM y Postgres reales: multi-intent funciona ("armame el plan, decime donde comer barato y si es seguro caminar de noche" ejecuta las 3 acciones), preguntas de recap se contestan desde el historial ("¿a qué destino dijimos que quería ir?"), "gracias" ya no devuelve una respuesta enlatada. `agente.py` pasa a ser una fachada delgada sobre el grafo; `test_agente.py` se reescribió para probar solo esa fachada, la lógica del orquestador en sí la prueba `test_grafo.py` (23 tests).

## D-13, persistencia de chats en Postgres

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Contexto:** `SesionAgente` (RF11) vivía solo en memoria del proceso: un refresh de página en la GUI, o cerrar el proceso del CLI, perdía toda la conversación. El usuario pidió explícitamente poder guardar charlas y volver a ellas.
- **Decisión:** `sql/002_conversaciones.sql` agrega dos tablas en la misma base que los vectores (mismo argumento que D-01: un solo motor). `mensaje` es la fuente de verdad del historial de texto. `conversacion.sesion` (jsonb) guarda solo el **estado derivado** (`PreferenciasViaje`, el último plan armado, qué destino ya mostró `info_destino`), nunca el historial: evita tener dos copias que puedan desincronizarse. `conversacion.esquema_version` permite que, si el modelo de `sesion` cambia más adelante, un chat viejo degrade a estado vacío al abrirlo (conserva igual el historial) en vez de romper.
- **Alternativas descartadas:** guardar todo (estado + historial) en un solo campo jsonb por conversación — descartado porque duplicaría el historial respecto de lo que necesita el prompt del LLM, y porque una tabla `mensaje` normal permite `ORDER BY orden` e índices sin tener que parsear jsonb grande en cada turno.
- **Consecuencias:** `conversaciones.py` (crear/listar/cargar/guardar_turno/renombrar/eliminar), verificado de punta a punta contra Postgres real (`test_conversaciones_db.py`, marcado `@pytest.mark.db`, se salta solo si no hay `TEST_DATABASE_URL`). La UI (`ui/chat_app.py`) se conectó a esto en el mismo día: sidebar con lista de chats, el chat activo vive en la URL (`st.query_params`) para sobrevivir un refresh.

## D-14, pregunta consolidada y derivación de tipo_destino (redefine la regla de "máx. 2 slots por turno" de `arquitectura.md`)

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Contexto:** dos bugs de fondo encontrados charlando con el agente. Primero, `tipo_destino` nunca se completa solo con palabras del usuario para una ciudad como Barcelona (nadie dice "quiero un destino de tipo ciudad"), así que quedaba faltante para siempre y la misma pregunta se repetía turno tras turno. Segundo, pedirle al LLM que redactara la pregunta por lo que falta (`PROMPT_PREGUNTAR_SLOTS_FALTANTES`, máximo 2 campos por turno) llegó a inventar una opción que no existe ("¿playa, ciudad, **montaña** o naturaleza?", ningún destino piloto es de montaña) y a presuponer datos no dados ("¿primera o segunda quincena de **este mes**?", sin que el usuario hubiera mencionado ningún mes).
- **Decisión:** (1) `tipo_destino` se deriva de `destinos.json` (`tipos` por destino piloto) en cuanto el destino está confirmado, nunca se vuelve a preguntar. (2) La pregunta por lo que falta se arma en Python (`preguntas.armar_pregunta_consolidada`), a partir de una tabla fija de opciones por campo, no vía LLM: todos los campos faltantes juntos en una sola pregunta (ya no el límite de 2 por turno), con opciones concretas y una sugerencia marcada por campo, más una salida "usar sugerencias" para que el cliente acepte un borrador de una sola vez.
- **Alternativas descartadas:** seguir pidiéndole al LLM que redacte la pregunta pero con una instrucción más estricta contra inventar opciones — descartado porque ya había una instrucción explícita contra inventar (ver P-07) y el modelo igual generó una pregunta presuntuosa; una tabla fija en código no tiene ese riesgo por construcción.
- **Consecuencias:** una llamada menos al LLM por turno (la pregunta ya no la redacta el modelo). Verificado con LLM real: Barcelona ya no repite la pregunta de tipo_destino, y la pregunta consolidada nunca menciona una opción fuera de la tabla. `PROMPT_PREGUNTAR_SLOTS_FALTANTES`, `PROMPT_CONFIRMAR_DESTINO_INFERIDO` y `MAXIMO_SLOTS_A_PREGUNTAR_POR_TURNO` se eliminan, ya no los usa nadie.

## D-15, justificaciones de RAG en un solo llamado por lote

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Contexto:** `recomendar_actividades`/`recomendar_locales` hacían una llamada al LLM **por cada resultado recuperado** (hasta k llamadas por turno), y `responder_faq_viajero` una por tema. Cuando el texto de un resultado no alcanzaba para justificarlo, esa llamada igual devolvía una frase tipo "el texto no alcanza para justificar la recomendación" que se mostraba como si fuera la recomendación en sí — una respuesta confusa — y cuando ningún tema de FAQ tenía la información pedida, el cliente veía la misma negativa repetida hasta 3 veces.
- **Decisión:** `justificacion.justificar_lote` hace **una** llamada estructurada que evalúa y justifica todos los resultados de una vez, marcando cada uno como relevante o no; los no relevantes se descartan antes de mostrar nada. `responder_faq_viajero` sintetiza **una** respuesta combinando los temas recuperados, con un flag `respondida` para el caso honesto de "no tengo esa información" (ahora se dice una sola vez, no una vez por tema).
- **Alternativas descartadas:** mantener una llamada por resultado pero filtrar client-side las respuestas que digan "no alcanza" — descartado porque sigue gastando k llamadas (relevante para P-08/latencia) y porque el LLM no siempre usa la misma frase para decir "no alcanza", un filtro de texto sería frágil.
- **Consecuencias:** de k+1 a 2 llamadas por turno de recomendación; de hasta 3 a 1 por turno de FAQ. Tests reescritos en `test_tools_rag.py` para el nuevo contrato (un solo llamado, respuesta sintetizada).

## D-16, `costos.py` como única fuente de costos, con gasto diario por presupuesto

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Contexto:** existían dos tablas de costo por categoría con valores distintos para las mismas categorías: una en `costos.py` (escrita pero nunca conectada) y otra inline en `armar_plan.py`. Además, `presupuesto` (dato que el cliente da en RF1) nunca afectaba el costo del plan: dos personas con presupuesto "bajo" o "alto" recibían el mismo número.
- **Decisión:** `costos.py` pasa a ser la única fuente. Se agrega `GASTO_DIARIO_POR_PERSONA[destino][presupuesto]`, una estimación ilustrativa (comida + transporte local) que se suma al costo de las actividades del día. Documentado como estimación de producto, no un dato de ninguna API en vivo (mismo criterio que ya declaraba `COSTO_BASE_POR_CATEGORIA`).
- **Alternativas descartadas:** pedirle el gasto diario a una API de costo de vida en vivo — descartado por agregar una dependencia externa nueva para un número que de todos modos es una estimación, no un precio real.
- **Consecuencias:** `PlanDeViaje` separa `costo_actividades_total` de `gasto_estimado_total`. `presupuesto` ahora cambia el costo final del plan (verificado en tests: Cancún/bajo vs Cancún/alto dan totales distintos para el mismo itinerario).

## D-17, corpus de atractivos: excluir edificios que no son atractivos, curar Miami y completar Cancún

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Contexto:** cargando el corpus real de punta a punta se encontró que 49 de los 75 "atractivos" de Miami eran torres de departamentos y hoteles (kind primario `skyscrapers`/`resorts` de OpenTripMap, con `architecture` como kind secundario, se colaban igual por el filtro de intersección de D-07). Un plan armado con esos datos para "playa y vida nocturna" recomendaba visitar edificios residenciales, no una sola playa. Por separado, Cancún volvió a caer por debajo del mínimo de 20 atractivos reales (la caché de `data/raw/cancun_detalles.json` de esta máquina ya no rendía los 7 de OpenTripMap que documentaba `estado.md`; re-ingestado con radio de 50km y filtro `rate` relajado, siguió dando 0).
- **Decisión:** `normalizar.py` excluye POIs cuyo kind **primario** esté en `CATEGORIAS_EXCLUIDAS_COMO_PRIMARIO` (`skyscrapers`, `resorts`, `accomodations`, `other_buildings`), a diferencia del filtro de inclusión (por intersección) que ya existía. Se cura a mano, verificado contra Wikipedia, un corpus nuevo de 10 lugares reales de Miami (South Beach, Wynwood Walls, Little Havana, Vizcaya...) para compensar la exclusión, y 7 atractivos más de Cancún (llega a 20/20 solo con datos curados). `scripts/cargar_todos.py --reemplazar` borra las filas de un destino antes de recargarlo, porque el upsert por xid actualiza o agrega pero nunca borra una fila cuyo xid ya no se genera con la nueva regla.
- **Alternativas descartadas:** filtrar por kind secundario también (excluir cualquier POI que tenga `skyscrapers` en la lista, no solo como primario) — descartado porque un atractivo real puede tener `architecture` como kind secundario sin ser una torre genérica; filtrar por intersección completa hubiera sido demasiado agresivo.
- **Consecuencias:** los 3 destinos piloto quedan por encima del mínimo con `scripts/verificar_corpus.py` (Barcelona 39, Cancún 20, Miami 35 atractivos, cero duplicados, cero rascacielos). Verificado con un plan real para Miami/playa/vida nocturna: ya no aparece ningún edificio.

## D-18, RF6/RF7 (alojamiento y vuelos) enganchados al grafo, con sus propias precondiciones

- **Fecha:** 2026-09-17
- **Fase:** 7D
- **Contexto:** `buscar_alojamiento`/`buscar_vuelos` ya existían como tools standalone (D-05/D-06) pero `planificar`/`ejecutar_acciones` de `grafo.py` (D-12) nunca las llamaba: pedirle alojamiento o vuelos al agente conversacional no hacía nada.
- **Decisión:** se agregan como `TipoAccion` más en `AccionPedida`, con precondición propia en `planificar`: ambas necesitan fechas exactas de ida y vuelta (no alcanza con `duracion_dias`), y vuelos además necesita `origen`; si falta algo, se agrega un pseudo-fragmento (`pedir_fechas_exactas`/`pedir_origen_vuelo`) en vez de llamar la tool con datos incompletos. `habitaciones` se deriva de `cantidad_personas` (`ceil(personas/2)`).
- **Alternativas descartadas:** dejar que la tool misma valide y devuelva un error de vuelta al LLM para que reformule la pregunta — descartado por el mismo criterio que el resto de `planificar`: las precondiciones son deterministas, no dependen de que el LLM interprete bien un error de tool.
- **Consecuencias:** verificado en vivo contra las APIs reales: una búsqueda de hoteles en Booking.com15 devolvió resultados reales; un timeout real de red en la búsqueda de vuelos cayó al fixture marcado como tal (regla dura 5), no a una excepción cruda.

## D-19, conversión de moneda en vivo, ARS por defecto

- **Fecha:** 2026-09-17
- **Fase:** 7D
- **Contexto:** pedido explícito del usuario. El público de este TP es de Argentina; el costo de un plan se calcula en USD (D-16), pero lo que le importa a un viajero argentino es cuánto sale en pesos, y a qué cotización (oficial vs. tarjeta cambian mucho).
- **Decisión:** `services/cambio.py` consulta dolarapi.com (sin API key) para ARS, con oficial y tarjeta por separado ya que un viajero paga con tarjeta el segundo, no el primero; para cualquier otra moneda, open.er-api.com. Cacheado 1 hora en memoria de proceso. Si ninguna fuente responde, se lo dice honestamente en vez de inventar un número (regla dura 5) o de dejar el turno sin respuesta.
- **Alternativas descartadas:** una tabla de cotizaciones fija en el código — descartada porque el dólar argentino cambia todos los días y una cifra hardcodeada sería mentira a los pocos días de la entrega.
- **Consecuencias:** `convertir_moneda` como acción nueva del grafo (D-12), con precondición propia (necesita un `ultimo_plan` armado; si no hay ninguno, pide armarlo primero). Verificado contra las APIs reales el mismo día (oficial 1535 / tarjeta 1995.5 ARS por USD).

## D-20, tarjetas HTML para los resultados del chat, no texto/markdown plano

- **Fecha:** 2026-09-17
- **Fase:** 7D
- **Contexto:** pedido explícito del usuario ("generar html integrado en el chat para... dar de una manera más linda, más presentable"). El plan de Fase 7C proponía una arquitectura de bloques tipados (`respuesta.py` + `presentacion/html.py`, un renderer por tipo de bloque) que nunca se construyó: el grafo quedó devolviendo texto plano con bullets markdown (`- **X**: Y`), igual que la Fase 7B.
- **Decisión:** en vez de la reescritura completa a bloques tipados (que hubiera tocado el contrato de `EstadoGrafo`/`Fragmento` y buena parte de los tests de `test_grafo.py`), se agrega `presentacion.py`: un helper de tarjeta HTML genérico (`tarjeta(titulo, filas, pie)`) más `escapar()`, y las funciones `_resumen_*` de `grafo.py` (que ya existían y ya se llamaban desde `ejecutar_acciones`) pasan a devolver esa tarjeta en vez de una lista de bullets. El contrato de `EstadoGrafo`/`Fragmento` no cambia: sigue siendo `texto: str`, solo que ese string ahora puede contener HTML. `ui/chat_app.py` renderiza con `st.markdown(..., unsafe_allow_html=True)` **solo para los mensajes del asistente**, nunca para lo que el usuario escribe (para no habilitar HTML sobre texto no controlado). `scripts/chat.py` (CLI secundario) usa `presentacion.texto_terminal()` para sacar las etiquetas antes de imprimir.
- **Alternativas descartadas:** la arquitectura de bloques tipados del plan original — descartada por costo/beneficio dado el calendario de entrega (30/09): el resultado visual pedido (tarjetas separadas del texto conversacional) se logra igual sin tocar el contrato del grafo ni los tests existentes. Queda como posible trabajo futuro si hace falta, por ejemplo, que la UI reaccione distinto a cada tipo de bloque (hoy es indiferente, todo es un string).
- **Consecuencias:** todo dato dinámico (nombre de una actividad, justificación de una recomendación, cotización) pasa por `escapar()` antes de entrar al HTML — verificado con un test que mete un `<script>` en un nombre y confirma que llega escapado. Verificado visualmente con Playwright: las tarjetas se ven como cajas separadas del texto, sin ninguna etiqueta HTML cruda visible en pantalla.

## D-21, `pedir_datos` recuerda qué faltantes ya preguntó, para no repetirse (P-13)

- **Fecha:** 2026-09-17
- **Fase:** 7D
- **Contexto:** corriendo `scripts/evaluar_conversaciones.py` de verdad contra Gemini se encontró (P-13) que `nodo_planificar` repetía la misma pregunta consolidada en cada turno mientras faltara algún dato, sin importar si el mensaje de ese turno era un agradecimiento u otro comentario sin datos nuevos.
- **Decisión:** nuevo campo de sesión `pedir_datos_mostrado_para: list[str] | None`, con el mismo patrón que `info_destino_mostrada_para` (persistido en `SesionAgente`/`conversacion.sesion`, threaded por `procesar_turno`). `pedir_datos` solo se agrega si los `faltantes` de este turno son distintos de los que ya se preguntaron, si el estado cambió (`detectar_cambios`), o si el cliente pidió algo explícito este turno.
- **Alternativas descartadas:** dejar que el LLM de `redactar` decida cuándo repetir la pregunta — descartado por el mismo criterio que el resto de `planificar` (D-14): la decisión de qué preguntar es determinista, no delegable al LLM turno a turno.
- **Consecuencias:** verificado en vivo, antes y después del fix, con el mismo escenario del harness (`agradecimiento_small_talk`): antes, "Gracias, me sirvió mucho" devolvía la pregunta de siempre; después, un agradecimiento contextual ("Me alegro mucho de que le haya servido... para su próximo viaje a Barcelona del 5 al 10 de marzo de 2027"). Tests nuevos en `test_grafo.py` cubren no-repetir / repetir-si-cambia-algo / repetir-si-hay-pedido-explícito / primera-vez / limpieza cuando ya no falta nada.

## D-22, el LLM redacta la respuesta de todos los turnos (redefine D-14, D-16 parcial y D-20)

- **Fecha:** 2026-09-23
- **Fase:** 7E
- **Contexto:** pedido explícito del usuario, con capturas de una conversación real. El asistente pidió "armame un borrador, pero dejá el último día libre, no pongas actividades" y devolvió un plan de 6 días con actividades los 6. Al reclamarlo dos veces más, con palabras cada vez más explícitas, devolvió **el mismo plan byte por byte las tres veces**. Diagnóstico: de las 5 llamadas al LLM del sistema, 4 eran `con_salida_estructurada` (rellenar un schema, no redactar), y el 100% del texto que ve el cliente salía de plantillas de Python (`preguntas.py`, `_resumen_*`, `presentacion.py`). La única ruta de texto libre era `PROMPT_CONVERSAR`, usada solo como *fallback* cuando no se había ejecutado ninguna acción, y acotada a "una o dos frases breves". D-14, D-15, D-16 y D-20 habían cambiado flexibilidad por determinismo una por una; apiladas, daban un agente incapaz de acusar recibo de nada.
- **Decisión:** invertir la responsabilidad de la redacción. `nodo_redactar` pasa a llamar al LLM en **todos** los turnos (`PROMPT_REDACTAR`) con los hechos del turno, y las tarjetas de datos se adjuntan debajo de esa prosa. `Fragmento` gana un campo `datos` (los hechos en texto plano, para el modelo) además de `texto` (la tarjeta HTML, para el cliente). Además `armar_plan` deja de ser una función pura de los slots: acepta `ajustes` (nuevo módulo `ajustes.py`) y reporta `ajustes_aplicados` / `ajustes_no_aplicados`, que el redactor usa para confirmar lo que se respetó o admitir lo que no se pudo.
- **La línea que se mantiene:** los datos duros (nombres de lugares, precios, fechas, clima, vuelos) siguen saliendo exclusivamente del corpus y de las tools, nunca del modelo — eso es lo que preserva la regla dura 5 y sigue siendo defendible. Lo que cambia es **quién escribe las oraciones**, no de dónde salen los hechos. Los consejos generales de viaje sí puede darlos el modelo, marcados como orientación general.
- **Alternativas descartadas:** (a) agregar más campos tipados al estado para cada cosa que el cliente pudiera pedir — descartada, y señalada por el propio usuario, porque es la enfermedad que causó el problema, no la cura; (b) dejar las plantillas y sumar solo una frase redactada alrededor — descartada porque el plan en sí seguía leyéndose enlatado.
- **Consecuencias:** `PROMPT_CONVERSAR` se elimina (queda cubierto por `PROMPT_REDACTAR`). Un llamado más al LLM por turno (cuota, latencia). Los tests del grafo dejan de asertar sobre prosa y pasan a verificar **qué hechos llegan al redactor** (`_hechos_del_turno`), que es el contrato real: asertar la redacción sería testear la salida de un modelo generativo. Se agrega una respuesta determinista de reserva por si la redacción falla (cuota agotada), para no dejar nunca al cliente sin respuesta. Verificado en vivo: pedir "dejame el último día libre" sobre un plan de Lisboa de 5 días ahora deja el día 5 sin actividades, baja el total de USD 556 a 526 y lo confirma en palabras.

## D-23, ingesta bajo demanda: el asistente responde por cualquier ciudad (redefine D-04)

- **Fecha:** 2026-09-23
- **Fase:** 7E
- **Contexto:** pedido explícito y repetido del usuario ("necesito que puedas entrar a todos los destinos a responder", "un chatbot que pueda responder todo sobre viajes y sea capaz de planificármelos"). Hasta acá el alcance eran 3 destinos piloto precargados a mano (D-04) y cualquier otro caía en `destino_fuera_de_alcance`. Se le advirtió al usuario que esto contradice la restricción de alcance del proyecto; decidió avanzar igual.
- **Decisión:** `destinos_bajo_demanda.asegurar_destino()`. Si el destino ya tiene corpus en pgvector se usa sin tocar la red; si no, se resuelve el nombre contra el endpoint `geoname` de OpenTripMap (nuevo `geolocalizar()`), se ingieren sus POIs, se embeben y se guardan. A partir de ahí queda cargado para siempre. El corpus crece solo, con datos reales, sin curaduría manual por ciudad.
- **Alternativas descartadas:** (a) cargar a mano 20+ destinos en `destinos.json` — descartada porque no escala, exige curaduría por ciudad (ver D-17) y sigue siendo una lista cerrada; (b) dejar que el LLM invente atractivos para destinos sin corpus — descartada, viola la regla dura 5.
- **Consecuencias:** `destino_fuera_de_alcance` queda solo para lugares que no existen (verificado: "Ciudad Inventada Xyzzy" se rechaza, Tokio/Roma/Lisboa/Kioto/Praga se ingieren). Los destinos piloto siguen teniendo prioridad de coordenadas curadas. `paises.json` se amplía a 56 países con su código ISO-2, porque el geocoder devuelve el país como código; si un país no está, se omiten idioma y moneda en vez de inventarlos. La primera mención de una ciudad nueva cuesta ~20s dentro del turno, lo que obligó a paralelizar el paso 2 de OpenTripMap (de 140s a ~20s) y a ingerir solo atractivos en el camino interactivo. El filtro de significancia (`rate=2`) pasa a ser el default de la ingesta: es lo que evita que el corpus de una ciudad se llene de edificios anónimos con artículo de Wikipedia, que es exactamente lo que le pasó a Barcelona.

