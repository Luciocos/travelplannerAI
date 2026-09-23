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

## P-08, la causa real de P-06 era el SDK reintentando en silencio, no el rotador

- **Fecha:** 2026-09-17
- **Fase:** 7C
- **Síntoma:** P-06 quedó documentado como "sin resolver": una llamada aislada tardaba hasta 42s sin que `RotadorClavesGemini` logueara ningún backoff ni rotación, así que no se sabía si el problema era cuota real o algo del propio rotador.
- **Causa:** `ChatGoogleGenerativeAI` trae `max_retries=6` por defecto, y el SDK `google-genai` reintenta un 429/503 con backoff exponencial propio (~1+2+4+8+16s) **antes** de que la excepción llegue al rotador. El rotador nunca veía el error: el SDK ya se había reintentado 6 veces solo, en la misma clave, por su cuenta.
- **Solución:** `max_retries=1` en el `ChatModel` (`crear_rotador`): el único que reintenta es el rotador propio, rotando de clave en vez de reintentando la misma. `_es_error_cuota` se amplía para tratar 503/504/UNAVAILABLE igual que 429.
- **Aprendizaje:** un wrapper propio de reintentos (el rotador) puede quedar completamente anulado si la librería de abajo ya trae su propio mecanismo de reintentos activado por defecto. Verificar siempre los valores por defecto del SDK antes de agregar una capa de resiliencia propia encima.

## P-09, con max_retries=1, un timeout no era un error "rotable"

- **Fecha:** 2026-09-17
- **Fase:** 7C, encontrado corriendo el orquestador nuevo contra Gemini real
- **Síntoma:** con el fix de P-08 en producción, una key lenta hacía fallar el turno completo en vez de rotar a las otras dos: `httpx.ReadTimeout: The read operation timed out` se propagaba crudo desde la primera clave.
- **Causa:** el mensaje de un `httpx.ReadTimeout` no contiene "429", "503" ni "unavailable", así que `_es_error_cuota` lo clasificaba como no-rotable y el rotador hacía `raise` inmediato en vez de probar la clave 2. El propósito del rotador (failover entre 3 claves) quedaba anulado justo para el tipo de error que `timeout=30` (agregado en P-08) iba a producir más seguido.
- **Solución:** `_es_error_cuota` también reconoce "timeout"/"timed out"/"deadline" como error rotable. Además, verificado en vivo que con `max_retries=1` un intento real (no colgado) puede tardar más de 30s bajo carga de sesión acumulada — la misma latencia de hasta 42s que ya documentaba P-06, no un cuelgue: `timeout` sube de 30 a 45 segundos para no cortar una respuesta legítima a mitad de camino.
- **Aprendizaje:** agregar un timeout a un cliente HTTP introduce un tipo de error nuevo; cualquier lógica de clasificación de errores escrita antes de agregar ese timeout (como `_es_error_cuota`) hay que revisarla, no asumir que sigue cubriendo todos los casos.

## P-10, mensajes con varios pedidos diluían la búsqueda semántica de cada uno

- **Fecha:** 2026-09-17
- **Fase:** 7C, encontrado probando el multi-intent del grafo nuevo contra Gemini real
- **Síntoma:** "armame el plan, decime donde comer barato y si es seguro caminar de noche" ejecutaba las 3 acciones (bien), pero la respuesta de seguridad no tenía nada que ver con caminar de noche: "los temas de referencia disponibles no contienen información para armarle un plan de viaje completo ni para indicarle dónde comer barato".
- **Causa:** `recomendar_locales` y `responder_faq_viajero` recibían el **mensaje completo** como consulta de búsqueda semántica, aunque el mensaje tuviera 3 pedidos mezclados. La consulta vectorial terminaba siendo un promedio confuso de "plan de viaje" + "dónde comer" + "seguridad nocturna", y el LLM de síntesis heredaba esa mezcla.
- **Solución:** `AccionPedida` suma un campo `consulta` opcional: `interpretar` completa el fragmento del mensaje que corresponde a ESA acción puntual cuando hay más de un pedido en el turno, y lo deja vacío (se usa el mensaje completo, mismo comportamiento que antes) cuando esa acción es el único pedido.
- **Aprendizaje:** soportar multi-intent en un orquestador no alcanza con decidir qué acciones ejecutar; cada acción que hace búsqueda semántica necesita también su propio fragmento de consulta, o la ganancia de "atender varios pedidos a la vez" se pierde en la calidad de cada respuesta individual. Esto no se ve mockeando el LLM en tests unitarios, solo probando con turnos reales que combinan pedidos.

## P-11, st.rerun() dentro del `with obtener_conexion()` deshacía su propia escritura

- **Fecha:** 2026-09-17
- **Fase:** 7D, encontrado probando en vivo con Playwright el botón de descarga de itinerario
- **Síntoma:** crear una conversación nueva desde la sidebar y enviar el segundo mensaje rompía con `psycopg.errors.ForeignKeyViolation: insert or update on table "mensaje" violates foreign key constraint "mensaje_conversacion_id_fkey" ... Key (conversacion_id)=(...) is not present in table "conversacion"`. Confirmado con `docker exec ... psql` que ese id, en efecto, nunca existió en la tabla `conversacion` (0 filas).
- **Causa:** `db.obtener_conexion()` es un context manager genérico: `except Exception: conexion.rollback(); raise`, correcto para cualquier error real. Pero los cuatro manejadores de botón de `_sidebar()` (nueva conversación, cambiar de chat, borrar, guardar renombre) llamaban `st.rerun()` **dentro** del `with obtener_conexion()` de `main()`. `st.rerun()` funciona lanzando una excepción interna de control de Streamlit, no un error; esa excepción atraviesa el `with` igual que cualquier otra, y el `except Exception` la trata como una falla real y deshace el `INSERT` recién hecho (la conversación nueva), aunque `st.session_state.chat_actual` ya apuntara a ese id ahora fantasma. El próximo mensaje enviado a ese chat fallaba por la foreign key.
- **Solución:** `_sidebar()` ya no llama `st.rerun()`; devuelve `bool` (`necesita_rerun`). El cuerpo de `main()` que antes vivía dentro del `with` se extrajo a `_cuerpo_principal(conexion) -> bool`, que también devuelve esa señal sin llamar `st.rerun()`. `main()` llama `st.rerun()` una sola vez, **después** de que el `with` cerró solo (y confirmó la escritura). Verificado en vivo con Playwright: crear un chat nuevo y enviar dos mensajes seguidos ya no rompe, y `docker exec ... psql` confirma que la conversación usada existe con sus 4 filas de `mensaje`.
- **Aprendizaje:** una excepción de control de un framework (`st.rerun()`, pero el mismo riesgo aplica a cualquier excepción "no-error" usada para cortar flujo, como `StopIteration` fuera de su lugar) puede activar por accidente un `except Exception` genérico de una capa inferior que no sabe distinguirla de un error real. La regla práctica: nunca llamar `st.rerun()` (ni nada que dependa de lanzar una excepción de control) desde dentro de un `with` que hace commit/rollback basado en `except Exception`; dejar que el `with` cierre primero.

## P-12, un test de la UI que parcheaba `asistente_viajes.agente.procesar_mensaje` pasaba solo en aislamiento

- **Fecha:** 2026-09-17
- **Fase:** 7D, escribiendo `test_ui_chat_app.py` con `streamlit.testing.v1.AppTest`
- **Síntoma:** un test que esperaba ver el mensaje de error de la UI cuando `procesar_mensaje` explota pasaba corriéndolo solo (`pytest tests/test_ui_chat_app.py::test_error...`), pero fallaba corriendo el archivo completo: seguía mostrando la respuesta "feliz" del test anterior, como si el `monkeypatch.setattr(agente, "procesar_mensaje", _falla)` de este test nunca se hubiera aplicado.
- **Causa:** `ui/servicio.py` hace `from asistente_viajes.agente import procesar_mensaje` (y lo mismo para las funciones de `conversaciones.py`). Esa línea solo se ejecuta la **primera** vez que algo importa `servicio` en todo el proceso: Python cachea el módulo en `sys.modules`, así que un `import servicio` posterior (el que hace `ui/chat_app.py` en cada `AppTest.from_file(...).run()`) no vuelve a ejecutar el cuerpo de `servicio.py`, solo reutiliza el mismo objeto módulo ya importado. El nombre `procesar_mensaje` dentro del namespace de `servicio.py` quedó fijado para siempre al valor que tenía `asistente_viajes.agente.procesar_mensaje` en el momento de esa primera importación (el mock del primer test); parchear `agente.procesar_mensaje` en un test posterior no tiene ningún efecto sobre esa copia ya congelada.
- **Solución:** parchear `servicio.py` directo (`servicio.procesar_mensaje = ...`, no `agente.procesar_mensaje = ...`). Dentro de `responder()`, la llamada a `procesar_mensaje(...)` resuelve ese nombre en el namespace global del propio módulo `servicio.py` **en el momento de la llamada**, no en el momento en que se definió la función, así que reasignar el atributo del módulo sí cambia el comportamiento de la próxima llamada, sin importar cuántas veces ya se haya importado.
- **Aprendizaje:** un `from X import Y` no es un alias vivo hacia `X.Y`; es una copia del valor de `Y` tomada en el instante del import. Parchear `X.Y` después de ese import no afecta a nadie que ya haya hecho `from X import Y` antes del parche. Para que un mock se vea reflejado en un módulo, hay que parchear el nombre en el namespace de ESE módulo (`modulo.nombre = ...`), no en el módulo de origen — que es exactamente el motivo de diseño por el que existe `ui/servicio.py` como capa intermedia (ver su propio docstring), pero hay que parchearlo ahí, no un nivel más abajo.

## P-13, "gracias" quedaba tapado por la misma pregunta consolidada de siempre

- **Fecha:** 2026-09-17
- **Fase:** 7D, encontrado corriendo `scripts/evaluar_conversaciones.py` de verdad contra Gemini (escenario `agradecimiento_small_talk`)
- **Síntoma:** con datos todavía incompletos (faltaba `intereses`), el turno "Gracias, me sirvió mucho" devolvía exactamente la misma pregunta consolidada de siempre ("¿Qué le interesa hacer...?") más "No encontré actividades para recomendarle con esos intereses en este destino." — ninguna referencia al agradecimiento.
- **Causa:** `nodo_planificar` agregaba `pedir_datos` (más la recomendación de regalo) de forma incondicional en **cada** turno mientras `faltantes` no estuviera vacío, sin importar si el mensaje de ese turno aportaba algo nuevo o no. Un comentario suelto sin datos nuevos (un agradecimiento, un "ok", cualquier small talk) disparaba la misma pregunta otra vez en vez de caer en `redactar`/`conversar`, que sí tiene el contexto para responder algo relevante.
- **Solución:** nuevo campo de sesión `pedir_datos_mostrado_para` (mismo patrón que `info_destino_mostrada_para`): guarda qué `faltantes` se preguntaron la última vez. `pedir_datos` solo se agrega si esos faltantes cambiaron, si el estado cambió este turno (`detectar_cambios`), o si el cliente pidió algo explícito — nunca si es exactamente la misma pregunta de antes y el turno no aportó nada. Se limpia a `None` en cuanto no falta más nada.
- **Aprendizaje:** una lógica 100% determinística de "qué preguntar" (D-14, sin LLM) todavía necesita saber **si ya preguntó lo mismo antes** para no repetirse ante un turno que no aporta nada — eso no se resuelve solo con evaluar el estado actual, hace falta memoria de qué se mostró en el turno anterior (el mismo patrón que ya existía para `info_destino`). Encontrado corriendo el harness de verdad, no con mocks: los tests unitarios con un rotador mockeado no ejercitan una secuencia real de 2+ turnos con un mensaje de puro small talk en el medio.

## P-14, el agente devolvía el mismo plan byte por byte ante cualquier pedido de cambio

- **Fecha:** 2026-09-23
- **Fase:** 7E, encontrado por el usuario charlando con la app y reportado con capturas
- **Síntoma:** "armame un borrador, pero dejá el último día libre, no pongas actividades" devolvió un plan de 6 días con actividades los 6. El usuario lo reclamó dos veces más, cada vez más explícito ("no me dejaste el día libre (osea el día 6)", "liberame el día 6"), y recibió **el mismo plan idéntico las tres veces**. Además: pidió 5 días y le armó 6, y pidió gastronomía y le dio arquitectura.
- **Causa:** tres causas distintas apiladas. (1) `armar_plan(conexion, estado)` era una función **pura de los slots**: mismos slots, mismo plan, y no existía ninguna ruta de "modificar el plan existente". (2) `PreferenciasViaje` tenía 9 campos fijos y ninguno para restricciones, así que "dejá el último día libre" no tenía dónde aterrizar y se descartaba en la extracción. (3) El prompt de extracción nunca decía que `fecha_inicio` y `fecha_fin` son **inclusivas**, mientras `_cantidad_dias` calcula `(fin - inicio).days + 1`: el modelo ponía fin = inicio + 5 y salían 6 días. Lo de la gastronomía era un cuarto problema, de datos: el corpus de Barcelona nunca se curó (D-17 solo cubrió Miami y Cancún) y no tiene un solo atractivo gastronómico — ni la Sagrada Familia, dicho sea de paso.
- **Solución:** módulo `ajustes.py` y campo `ajustes` en el estado, sumado a `CAMPOS_QUE_AFECTAN_EL_PLAN` para que un cambio de ajustes dispare el re-armado que ya existía; `armar_plan` los aplica y reporta qué pudo y qué no; el redactor (D-22) confirma o admite el límite en palabras. La regla de fechas inclusivas se explicitó en el prompt con un ejemplo.
- **Aprendizaje:** el detalle más incómodo es que `armar_plan.py` **ya tenía** `NOMBRE_DIA_LIBRE` y `_actividad_dia_libre()`, pero solo como fallback para cuando el corpus se quedaba sin candidatos: la capacidad existía y era inalcanzable para el usuario. Vale como recordatorio de que "está implementado" y "el cliente puede llegar a eso" son dos cosas distintas. El segundo aprendizaje es de proceso: ninguno de los 248 tests detectó nada de esto, porque todos verificaban que las funciones hicieran lo que hacían, no que el asistente hiciera caso. Lo encontró un usuario hablándole a la app cinco minutos.

## Candidatos previsibles, confirmar si pasan de verdad

No inventar entradas. Estos son los puntos donde es probable que algo falle, listados para que se registren bien si ocurren:

- Cuota o caída de la API de OpenTripMap durante el desarrollo.
- Extractos de Wikipedia en inglés mezclados con consultas en español, y el efecto en la recuperación.
- El agente eligiendo la tool equivocada por un docstring ambiguo.
- Slot filling que repregunta algo ya respondido, o que pisa un slot cargado con None.
- Open-Meteo sin pronóstico para fechas a más de 16 días.
