# Estado del proyecto

**Archivo vivo. Leer al empezar cada sesión, actualizar al cerrar cada fase.**

Última actualización: 2026-09-23 (Fase 7E en curso, rama `fase/7e-flexibilidad`)

---

## Configuración del proyecto

| Campo | Valor |
|-------|-------|
| Repo | https://github.com/Luciocos/travelplannerAI |
| Integrantes | Lucio Cosentino; Joaquin Carlos Fernandez Da Silva; Aaron de Bernardo; Elias Danteo |
| Turno y fecha de defensa | (pendiente) |
| Destinos | **Cualquier ciudad, vía ingesta bajo demanda (D-23)**. Barcelona, Miami y Cancún siguen siendo los curados a mano (D-04). `data/reference/destinos.json` tiene coordenadas, `tipos` (deriva `tipo_destino`, D-14) y `descripcion` (para destinos sugeridos cuando no hay destino aún). |
| LLM | Gemini, `gemini-3.5-flash-lite` vía `GEMINI_MODEL` (D-03). `max_retries=1` y `timeout=45s` en el ChatModel (P-08/P-09): el SDK traía reintentos internos que escondían el failover del rotador. |
| Claves de Gemini | 3 cargadas en `.env` local. `smoke_llm.py` responde 3/3. Repository secrets de GitHub, pendientes de cargar. |
| Límite diario real por clave | Sigue sin poder verificarse de forma estática (bloqueo abierto, ver abajo). |
| Postgres | Local vía `docker-compose` (`DATABASE_URL` en `.env` apunta a `localhost:5432`). Esquema en 2 archivos, `sql/001_schema.sql` y `sql/002_conversaciones.sql` (D-13); `scripts/inicializar_db.py` aplica todos los `sql/*.sql` en orden. |

## Fase actual: Fase 7E, en curso (rama `fase/7e-flexibilidad`)

Abierta el 2026-09-23 a partir de un reporte del usuario con capturas: el agente era rígido, no aceptaba ningún cambio y repetía el mismo plan. El diagnóstico fue más de fondo que un bug (ver P-14 y D-22). Lo hecho hasta ahora, todo commiteado en la rama:

- **El LLM redacta todos los turnos (D-22).** Antes solo escribía cuando no había pasado nada; el resto eran plantillas de Python. Ahora `nodo_redactar` llama al modelo siempre con los hechos del turno y las tarjetas se adjuntan debajo. Se eliminó `PROMPT_CONVERSAR`.
- **El plan se puede ajustar (D-22).** Nuevo `ajustes.py` y campo `ajustes` en el estado: días libres, exclusiones y ritmo. `armar_plan` dejó de ser una función pura de los slots y reporta qué aplicó y qué no.
- **Cualquier destino (D-23).** `destinos_bajo_demanda.asegurar_destino()`: geocodifica con el `geoname` de OpenTripMap, ingiere, embebe y cachea en pgvector. Verificado con Roma (51 atractivos), Kioto (53), Lisboa (22), Praga (16), Estambul; "Ciudad Inventada Xyzzy" se rechaza bien.
- **Off-by-one de fechas.** El prompt no decía que las fechas son inclusivas y un viaje de 5 días salía de 6.
- **Tarjetas rehechas.** Tres columnas (día, actividades, costo), sin emoji, funcionando en tema claro y oscuro.
- **Iconos de la sidebar.** Los botones de renombrar y eliminar salían vacíos en Chrome/macOS: eran emoji, ahora son iconos Material.

Suite completa en verde (248 passed, 5 skipped) y ruff limpio en cada commit.

**Pendiente de esta fase:**
- Que el usuario lo pruebe en vivo (es el próximo paso inmediato).
- Curar o re-ingerir Barcelona con `rate=2`: su corpus viejo son casas anónimas, cines y teatros, sin la Sagrada Familia y sin nada gastronómico.
- Evaluar la Etapa 2 conversada con el usuario: reemplazar el pipeline rígido por un agente de tool-calling de LangGraph usando las `@tool` que ya existen y hoy están desconectadas.
- Mergear a `main` cuando el usuario dé el visto bueno.

## Fase 7D, mergeada a main

Rama `fase/7d-extensiones`, creada desde `main` justo después de mergear el notebook (commit `db3c598`). Fase 7C + el notebook ya estaban en `main`. Esta rama agregó lo que había quedado afuera de 7C: RF6/RF7 enganchados, conversión de moneda, descarga de itinerario, tarjetas HTML en el chat, harness de evaluación y tests de `AppTest`. Se encontraron y arreglaron 3 bugs reales probando todo esto en vivo: P-11 (UI), P-12 (tests) y P-13 (conversación). **Mergeada a `main` y pusheada el 2026-09-21** (commit de merge `0484775`, pedido explícito del usuario para que el equipo, Elias, pueda testear), previa corrida de la suite completa (248 passed, 5 skipped).

**Lo que se agregó, de mayor a menor impacto:**

- **RF6/RF7 enganchados al grafo (D-18).** `buscar_alojamiento`/`buscar_vuelos` ahora son acciones reales de `planificar`/`ejecutar_acciones` en `grafo.py`, con sus precondiciones (fechas exactas; vuelos además necesita `origen`). Verificado en vivo: una búsqueda real de hoteles en Booking.com15 funcionó; un timeout real de red en vuelos cayó correctamente a un fixture marcado como tal.
- **Conversión de moneda (D-19).** `services/cambio.py` + `tools/convertir_moneda.py`: USD→ARS (oficial y tarjeta, dolarapi.com) y USD→otras monedas (open.er-api.com), cacheado 1h, nunca inventa una cotización. Convierte por defecto el total del último plan armado. Verificado contra las APIs reales.
- **Descarga de itinerario.** `armar_plan.resumen_markdown()` + `servicio.itinerario_descargable()`: botón en la UI que exporta el plan armado a Markdown.
- **Tarjetas HTML en el chat (D-20).** `presentacion.py` (nuevo): un helper de tarjeta HTML genérico + `escapar()`. Las funciones `_resumen_*` de `grafo.py` (plan, actividades, locales, alojamiento, vuelos, info de destino) devuelven una tarjeta en vez de bullets de markdown; `ui/chat_app.py` renderiza con `st.markdown(..., unsafe_allow_html=True)` solo para los mensajes del asistente. No se hizo la arquitectura de bloques tipados del plan original de 7C (`respuesta.py`); se logra el resultado visual pedido sin tocar el contrato de `EstadoGrafo`. Verificado con Playwright: tarjetas visibles como cajas separadas, cero HTML crudo en pantalla.
- **Harness de evaluación (`scripts/evaluar_conversaciones.py`).** Corre escenarios guionados (`scripts/escenarios_conversacion.json`, 7 escenarios) contra Gemini y Postgres reales, turno a turno, con checks `debe_contener`/`no_debe_contener`, y escribe un reporte en `docs/evaluacion/`. Nunca se corre en CI (consume cuota real); es un script manual, como el resto de la verificación con LLM real de este proyecto. Corrido de punta a punta: 11/11 turnos OK, reporte commiteado como evidencia.
- **Tests de la UI con `streamlit.testing.v1.AppTest` (`tests/test_ui_chat_app.py`).** 7 tests: carga sin errores, botones de arranque, click de sugerencia + respuesta, historial persistido entre turnos, camino de error sin romper la app, ausencia del botón de descarga sin plan, y una regresión de P-11. Ningún test toca Postgres ni Gemini real.
- **P-11 (bug real, ver DIFICULTADES).** `st.rerun()` llamado desde dentro del `with obtener_conexion()` de `ui/chat_app.py` hacía rollback de la propia escritura que acababa de confirmar (crear/cambiar/borrar/renombrar un chat), dejando `session_state` apuntando a una conversación fantasma nunca persistida → `ForeignKeyViolation` al mandar el siguiente mensaje. Encontrado y arreglado probando en vivo con Playwright el botón de descarga; `_sidebar()`/`_cuerpo_principal()` ahora devuelven un `bool` en vez de llamar `st.rerun()` directo, y `main()` lo llama una sola vez después de que el `with` cerró y confirmó.
- **P-12 (bug real, ver DIFICULTADES).** Escribiendo `test_ui_chat_app.py`, parchear `asistente_viajes.agente.procesar_mensaje` pasaba en aislamiento pero fallaba corriendo el archivo completo: `ui/servicio.py` hace `from asistente_viajes.agente import procesar_mensaje` una sola vez por proceso (Python cachea el módulo), así que un parche posterior al original no llega a la copia ya congelada. Se parchea `servicio.py` directo, que es el que resuelve ese nombre en su propio namespace en cada llamada.
- **P-13, D-21 (bug real, ver DIFICULTADES/DECISIONES).** Corriendo el harness de verdad se encontró que `nodo_planificar` repetía la misma pregunta consolidada en cada turno mientras faltara algún dato, aunque el mensaje fuera un agradecimiento sin datos nuevos ("gracias" quedaba tapado). Nuevo campo de sesión `pedir_datos_mostrado_para` (mismo patrón que `info_destino_mostrada_para`): solo repregunta si los faltantes cambiaron, si el estado cambió, o si el cliente pidió algo explícito. Verificado antes/después con el mismo escenario real.
- **Sidebar movida al chat principal.** Los botones "Para arrancar" ya no viven en la sidebar; se muestran en el área central, solo cuando el chat está vacío (pedido explícito del usuario con screenshot). Este cambio se hizo antes de crear `fase/7d-extensiones` y viajó con Fase 7C a `main`.

**No hecho todavía** (quedan para la próxima sesión, ninguno bloquea lo demás):
- Repository secrets de GitHub y protección de `main` (bloqueo, requiere acceso del usuario/equipo a GitHub).

## Fases cerradas

- **Fases 0 a 6** (núcleo, RF1/RF2/RF3/RF5/RF11/RF12): cerradas en sesiones anteriores. Con el núcleo cerrado el TP ya era aprobable según `plan-de-fases.md`.
- **Fase 7C** (orquestador LangGraph + persistencia de chats + fine-tuning conversacional): cerrada y **mergeada a `main`**.
- **Fase 7D**: RF6/RF7 enganchados, moneda, descarga de itinerario, tarjetas HTML, harness de evaluación, tests de `AppTest`, P-11, P-12, P-13. **Mergeada a `main`** (commit `0484775`, 2026-09-21).

## Decisiones tomadas

Una línea por decisión, el detalle va en `docs/DECISIONES.md` del repo. D-01 a D-11: ver commits anteriores de este archivo / `docs/DECISIONES.md`. Nuevas en Fase 7C y 7D:

- **D-12:** orquestador migrado a LangGraph, redefine D-08 (un solo llamado de clasificación ya no alcanzaba para multi-intent ni memoria de conversación).
- **D-13:** persistencia de chats en Postgres (`conversacion`/`mensaje`), mismo motor que los vectores.
- **D-14:** pregunta consolidada armada en Python (no LLM), `tipo_destino` derivado del destino. Redefine la regla de "máx. 2 slots por turno" de `arquitectura.md`.
- **D-15:** justificaciones de RAG en un solo llamado por lote, no uno por resultado.
- **D-16:** `costos.py` única fuente de costos, gasto diario por presupuesto.
- **D-17:** exclusión de POIs que son edificios (no atractivos), curaduría de Miami y Cancún.
- **D-18 (Fase 7D):** RF6/RF7 enganchados al grafo, con precondición propia (fechas exactas, vuelos además `origen`).
- **D-19 (Fase 7D):** conversión de moneda vía dolarapi.com (ARS oficial/tarjeta) y open.er-api.com (otras monedas), cacheada 1h, nunca inventada.
- **D-20 (Fase 7D):** tarjetas HTML para los resultados del chat (`presentacion.py`), sin la reescritura a bloques tipados que proponía el plan original de 7C.
- **D-21 (Fase 7D):** `pedir_datos_mostrado_para` recuerda qué faltantes ya se preguntaron, para no repetir la misma pregunta ante un turno sin datos nuevos (P-13).

Decisiones que vienen dadas y no se rediscuten sin motivo nuevo:

- LangChain (+ LangGraph desde D-12) como framework base, requisito textual de la cátedra.
- PostgreSQL con pgvector como vector store, pedido explícito del profesor.
- Booking.com Demand API descartada por requerir aprobación de partner.
- Alcance acotado a 3 destinos piloto: Barcelona, Miami, Cancún.
- Gemini con modelo Flash Lite y rotación de 3 claves.
- Embeddings locales con sentence-transformers.
- Ningún commit lleva trailers de coautoría.
- Ningún workflow automático de CI consume cuota de LLM.

## Decisiones abiertas

- **Fase 2 (heredada):** `langchain_postgres.PGVector` contra tabla propia envuelta en un `BaseRetriever`. Se sigue con la tabla propia; migrar si conviene antes de la defensa.
- **CrewAI:** sólo si el usuario trae confirmación explícita del profesor. Por defecto, no.
- **Supabase vs Postgres local:** sigue sin resolverse con el equipo (ver bloqueos).

## Bloqueos

- **Límite diario/por minuto real por clave de Gemini sigue sin poder verificarse de forma estática.** Mitigado en la práctica por P-08/P-09 (el rotador ahora rota de verdad ante 429/503/504/timeout), pero el número real sigue sin confirmarse contra `aistudio.google.com/rate-limit`.
- **Decisión pendiente con el equipo: seguir en Postgres local o migrar a Supabase.**
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados. Requiere acceso del usuario/equipo a la configuración de GitHub, no se puede resolver solo desde el código.

## Próximo paso

1. Cargar los repository secrets en GitHub y proteger `main` (bloqueo, requiere al usuario).
2. Opcional: correr el resto de los escenarios de `scripts/evaluar_conversaciones.py` para tener más evidencia real en `docs/evaluacion/` antes de la defensa.

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
