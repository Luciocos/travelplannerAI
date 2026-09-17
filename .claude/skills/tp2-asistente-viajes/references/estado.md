# Estado del proyecto

**Archivo vivo. Leer al empezar cada sesión, actualizar al cerrar cada fase.**

Última actualización: 2026-09-17

---

## Configuración del proyecto

| Campo | Valor |
|-------|-------|
| Repo | https://github.com/Luciocos/travelplannerAI |
| Integrantes | Lucio Cosentino; Joaquin Carlos Fernandez Da Silva; Aaron de Bernardo; Elias Danteo |
| Turno y fecha de defensa | (pendiente) |
| Destinos piloto | Barcelona, Miami, Cancún (D-04). `data/reference/destinos.json` tiene coordenadas, `tipos` (deriva `tipo_destino`, D-14) y `descripcion` (para destinos sugeridos cuando no hay destino aún). |
| LLM | Gemini, `gemini-3.5-flash-lite` vía `GEMINI_MODEL` (D-03). `max_retries=1` y `timeout=45s` en el ChatModel (P-08/P-09): el SDK traía reintentos internos que escondían el failover del rotador. |
| Claves de Gemini | 3 cargadas en `.env` local. `smoke_llm.py` responde 3/3. Repository secrets de GitHub, pendientes de cargar. |
| Límite diario real por clave | Sigue sin poder verificarse de forma estática (bloqueo abierto, ver abajo). |
| Postgres | Local vía `docker-compose` (`DATABASE_URL` en `.env` apunta a `localhost:5432`). Esquema en 2 archivos, `sql/001_schema.sql` y `sql/002_conversaciones.sql` (D-13); `scripts/inicializar_db.py` aplica todos los `sql/*.sql` en orden. |

## Fase actual: Fase 7C, fine-tuning del agente conversacional

Rama `fase/7c-agente-conversacional` (desde `fase/0-scaffolding`), todavía no mergeada. El núcleo (Fases 0-6) y las extensiones adelantadas (RF6-RF9) seguían cerrados y verificados de una sesión anterior, pero **charlar libremente con el agente** (no solo casos de prueba guionados) encontró bugs de fondo en el diseño del orquestador de una sola tool por turno (D-08). Esta fase es una reescritura dirigida a arreglarlos, confirmada por el usuario. 21+ commits, cada uno con tests en verde (`ruff check`, `ruff format --check`, `pytest`).

**Lo que cambió, de mayor a menor impacto:**

- **Orquestador migrado a LangGraph (D-12, redefine D-08).** `grafo.py`: `interpretar` (un llamado que extrae datos Y decide 1-3 acciones por turno) → `actualizar_estado` (determinístico) → `planificar` (determinístico: pregunta consolidada + regalo si falta algo, re-arma el plan si cambió un dato relevante) → `ejecutar_acciones` (cada acción con su try/except propio) → `disparar_info_destino` → `redactar` (solo llama al LLM si no se ejecutó ninguna acción: recap, small talk). Soporta multi-intent real ("armame el plan, decime donde comer y si es seguro de noche" ejecuta las 3). **Verificado con LLM y Postgres reales.**
- **Persistencia de chats (D-13).** `sql/002_conversaciones.sql` + `conversaciones.py`: crear/listar/cargar/guardar_turno/renombrar/eliminar. La UI (`ui/chat_app.py`) tiene sidebar con chats guardados; el chat activo vive en la URL, sobrevive un refresh. Verificado contra Postgres real (`test_conversaciones_db.py`, `@pytest.mark.db`) y visualmente con Playwright (Chrome de Claude no estaba disponible esta sesión).
- **Pregunta consolidada sin LLM (D-14).** `preguntas.py` arma en Python la pregunta por todo lo que falta, con opciones concretas y "usar sugerencias"; cero riesgo de inventar una opción (antes pasó: "¿playa, ciudad, **montaña** o naturaleza?"). `tipo_destino` se deriva del destino piloto, nunca se pregunta.
- **RAG por lote (D-15).** Justificaciones de `recomendar_actividades`/`recomendar_locales` en un solo llamado (antes, uno por resultado); `responder_faq_viajero` sintetiza una sola respuesta (antes repetía la misma negativa hasta 3 veces).
- **Costos consolidados + gasto diario por presupuesto (D-16).**
- **Corpus de atractivos limpio (D-17).** Se excluyen POIs cuyo kind primario es un edificio (torres/hoteles: Miami tenía 49/75 "atractivos" que eran esto). Curaduría nueva: 10 lugares de Miami, 7 más de Cancún (llega a 20/20). `scripts/cargar_todos.py --reemplazar` + `scripts/verificar_corpus.py`.
- **P-06 resuelto de fondo (P-08, P-09).** La causa real no era el rotador: el SDK de Gemini reintenta 6 veces por su cuenta antes de que el rotador vea el error. `max_retries=1` en el ChatModel.

**Verificado con LLM y Postgres reales, no solo mocks:** recap ("¿a qué destino dijimos?" contestado desde el historial, no una frase enlatada), Barcelona ya no repite la pregunta de tipo_destino, "Quiero ir a Tokio" explica que no es un destino piloto y sugiere los 3 reales, multi-intent ejecuta las 3 acciones pedidas con su propia consulta cada una (P-10), un plan de Miami para "playa y vida nocturna" ya no recomienda edificios.

**No hecho en esta fase** (quedan para la próxima sesión, ninguno bloquea lo demás):
- Presentación HTML enriquecida en el chat (quedó en texto/markdown plano, como ya tenía Fase 7B).
- RF6/RF7 (alojamiento y vuelos) sin enganchar al orquestador nuevo (las tools existen y siguen funcionando standalone, D-05/D-06, pero `planificar`/`ejecutar_acciones` de `grafo.py` no las llama todavía).
- Conversión de moneda (pedido del usuario, no arrancado).
- `scripts/evaluar_conversaciones.py` (harness de evaluación con escenarios guionados contra LLM real) no escrito; la verificación de esta fase fue manual.
- **El notebook (`notebooks/demo_tp2.ipynb`) sigue vacío. Es el entregable oficial de la cátedra** (ver `consigna-catedra.md`) y no se tocó en esta fase — priorizar antes de la entrega del 30/09.
- `test_ui_chat_app.py` con `streamlit.testing.v1.AppTest` no escrito (la UI se verificó a mano con Playwright, no hay test automatizado de la capa de Streamlit todavía).

## Fases cerradas

- **Fases 0 a 6** (núcleo, RF1/RF2/RF3/RF5/RF11/RF12), **RF6-RF9** (extensiones adelantadas): cerradas en sesiones anteriores, ver commits `fase/0-scaffolding` previos a esta fase. Con el núcleo cerrado el TP ya era aprobable según `plan-de-fases.md`.
- **Fase 7C** (este documento): reescritura del orquestador y fine-tuning conversacional, ver arriba. Técnicamente completa para lo que cubre; **pendiente de confirmación formal del usuario antes de mergear a `main`**, igual que el núcleo.

## Decisiones tomadas

Una línea por decisión, el detalle va en `docs/DECISIONES.md` del repo. D-01 a D-11: ver commits anteriores de este archivo / `docs/DECISIONES.md`. Nuevas en Fase 7C:

- **D-12:** orquestador migrado a LangGraph, redefine D-08 (un solo llamado de clasificación ya no alcanzaba para multi-intent ni memoria de conversación).
- **D-13:** persistencia de chats en Postgres (`conversacion`/`mensaje`), mismo motor que los vectores.
- **D-14:** pregunta consolidada armada en Python (no LLM), `tipo_destino` derivado del destino. Redefine la regla de "máx. 2 slots por turno" de `arquitectura.md`.
- **D-15:** justificaciones de RAG en un solo llamado por lote, no uno por resultado.
- **D-16:** `costos.py` única fuente de costos, gasto diario por presupuesto.
- **D-17:** exclusión de POIs que son edificios (no atractivos), curaduría de Miami y Cancún.

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
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados.
- **El notebook no existe.** Es el entregable oficial, y el video/defensa dependen de él. Con la entrega el 30/09, esto es lo más urgente después de confirmar el cierre de Fase 7C.

## Próximo paso

1. Confirmar el cierre de Fase 7C con el usuario.
2. Evaluar si completar lo que quedó afuera de esta fase (RF6/RF7 enganchados al grafo, conversión de moneda, HTML en el chat, harness de evaluación) o pasar directo al notebook — **el notebook es lo más urgente dado el calendario de entrega**.
3. Escribir `notebooks/demo_tp2.ipynb` (estructura fija en `plan-de-fases.md`, Fase 8).
4. Cargar los repository secrets en GitHub y proteger `main`.
5. Mergear `fase/7c-agente-conversacional` (con `fase/0-scaffolding` adentro) a `main`.
6. `docs/DECISIONES.md`/`docs/DIFICULTADES.md` cerrados, `README.md` actualizado (Fase 9).

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
