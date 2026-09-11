# Estado del proyecto

**Archivo vivo. Leer al empezar cada sesión, actualizar al cerrar cada fase.**

Última actualización: 2026-09-10

---

## Configuración del proyecto

| Campo | Valor |
|-------|-------|
| Repo | https://github.com/Luciocos/travelplannerAI |
| Integrantes | Lucio Cosentino; Joaquin Carlos Fernandez Da Silva; Aaron de Bernardo; Elias Danteo |
| Turno y fecha de defensa | (pendiente) |
| Destinos piloto | Barcelona (ex "Europa"), Miami, Cancún / Riviera Maya (ex "Caribe"). Resuelto por D-04 en `docs/DECISIONES.md`, coordenadas concretas todavía sin cargar en `data/reference/`. |
| LLM | Gemini, `gemini-3.5-flash-lite` vía `GEMINI_MODEL`. **Confirmado contra la API real** (D-03): `gemini-2.5-flash-lite` da 404 para estas cuentas ("no longer available to new users"). |
| Claves de Gemini | 5 cargadas en `.env` local (`GEMINI_API_KEY_1` a `_5`). `smoke_llm.py` corrido a mano el 2026-09-10: **5/5 exitosas**. Repository secrets de GitHub, pendientes de cargar. |
| Límite diario real por clave | (pendiente de verificar en `aistudio.google.com/rate-limit` logueado, ver bloqueos — la doc pública ya no publica un número fijo) |
| Postgres | **Local vía `docker-compose` levantado y funcionando** (`DATABASE_URL` en `.env` apunta a `localhost:5432`), como paso intermedio mientras se resuelve Supabase (D-02) con el equipo. Esquema aplicado (`inicializar_db`), incluye `destino_externo` y `uso_api_mensual` (D-06). |

## Fase actual

**Núcleo completo (Fases 0 a 6, RF1/RF2/RF3/RF5/RF11/RF12) escrito, testeado y verificado de punta a punta contra infraestructura y APIs reales — Postgres local, OpenTripMap, Gemini real y Booking.com15 real, no solo mocks.** Según `plan-de-fases.md` (Fase 6), con el núcleo cerrado el TP ya es aprobable. **Pendiente de confirmación formal del usuario/equipo y de mergear a `main`**, pero el criterio técnico de cada fase ya se cumplió una por una:

- **Fase 0** (scaffolding): `docker-compose up -d` levantado y funcionando, esquema aplicado con `inicializar_db`, `smoke_llm.py` corrido a mano: **5/5 claves responden `200 OK`** con `gemini-3.5-flash-lite` (D-03).
- **Fase 1** (ingesta): los tres destinos superan el mínimo de atractivos (20, D-07) con datos reales — Barcelona 41, Miami 75 (ambos solo OpenTripMap), Cancún 20 (7 OpenTripMap + 13 curados, verificados por búsqueda web, `fuente='curado'`). RF4 (comercios) movido a extensión (D-07).
- **Fase 2** (vector store): los tres destinos cargados en `documento_rag` contra Postgres local con embeddings reales (Barcelona 43 docs, Miami 77, Cancún 20). Retrieval semántico verificado a mano.
- **Fase 3** (RF3, `recomendar_actividades`): **corrido con el LLM real** contra el corpus real de Cancún — recupera los lugares correctos y genera justificaciones que citan solo hechos del texto recuperado, nada inventado.
- **Fase 4** (RF1/RF2, `completar_slots`): **corrido con el LLM real**, dos turnos. No repisa lo ya cargado. Encontrado y corregido en el camino: `gemini-3.5-flash-lite` devuelve `.content` como lista de bloques, no string plano (nuevo helper `contenido_texto` en `llm.py`, afecta también `recomendar_actividades`/`recomendar_locales`). También se corrigió `plan-de-fases.md`: el criterio de aceptación original decía que el primer turno debía preguntar por "cantidad de personas y fechas", pero como el destino no está en el mensaje de ejemplo, lo correcto (y lo que efectivamente pasa) es preguntar primero por destino y tipo de destino.
- **Fase 6** (RF5, `armar_plan`, nuevo): itinerario día a día con costo estimado por una tabla fija de categoría (sin LLM). **Corrido contra el corpus real de Cancún**: itinerario de 3 días, 9 actividades sin repetir, persistido en `itinerario`/`itinerario_item`.
- **Fase 5** (RF11/RF12, orquestador, nuevo — `agente.py`): `SesionAgente` mantiene el estado entre turnos (RF11); en cada turno un LLM con salida estructurada decide sola qué tool corresponde (RF12), excepto `info_destino` que se dispara aparte, una sola vez, al confirmarse destino y fechas. **Verificado con una conversación real de 6 turnos** (LLM + corpus + Postgres reales): el estado se acumuló sin perder nada, la tool elegida en cada turno fue la correcta (`completar_slots` x4, `armar_plan`, `recomendar_locales`), `info_destino` se disparó exactamente una vez. El turno de comercios devolvió "no encontré locales" — correcto y esperado, es la limitación real y documentada de RF4 (D-07), no un bug. **Redefinido 2026-09-11 (D-10):** el orquestador ahora también elige `cantidad_resultados` (no solo la tool), sin pedirle nunca al LLM los parámetros que ya son estado validado (destino, intereses, fechas). **Re-verificado con LLM y Postgres reales**, conversación de 3 turnos: "dame 5 actividades" y "dame solo 1 opción de dónde comer" produjeron `cantidad_resultados=5` y `=1` correctamente, estado intacto en las 3 vueltas.
- **RF8** (clima + idioma/moneda, extensión adelantada): `tools/info_destino.py`, verificado dentro de la conversación de 6 turnos de arriba.
- **RF6/RF7** (alojamiento y vuelos, extensión adelantada): Amadeus dado de baja, migrado a RapidAPI/Booking.com15 (D-05/D-06). Verificado de punta a punta contra la base local y la API real.

101 tests unitarios (`pytest`) mockeados y en verde, más todas las verificaciones manuales reales de arriba. Lint (`ruff`) en verde. Venv local (`.venv`) armado porque esta máquina no tenía dependencias instaladas.

Todo en la rama `fase/0-scaffolding`, pusheada a origin, todavía no mergeada a `main`.

Falta para cerrar del todo: decidir con el equipo si se pasa a Supabase o se sigue en local por ahora, cargar los repository secrets de GitHub, confirmar el cierre de núcleo con el equipo, y mergear a `main`. Después de eso, extensiones (Fase 7: RF9 FAQ, RF10 gastos, retomar RF4 si hay tiempo).

## Fases cerradas

- **Fase 1** (ingesta), 2026-09-10: los tres destinos piloto superan el mínimo de atractivos (20) con datos reales, OpenTripMap + curaduría manual verificada por búsqueda web para Cancún. Comercios queda fuera del criterio (RF4 es extensión, D-07).
- **Fase 2** (vector store), 2026-09-10: los tres destinos cargados en `documento_rag` contra Postgres local con embeddings reales.
- **Fase 3** (RF3), 2026-09-11: `recomendar_actividades` corrido con LLM y corpus reales.
- **Fase 4** (RF1/RF2), 2026-09-11: `completar_slots` corrido con LLM real, dos turnos, sin repisar lo cargado.
- **Fase 6** (RF5), 2026-09-11: `armar_plan` corrido contra corpus real, persistencia verificada.
- **Fase 5** (RF11/RF12), 2026-09-11: orquestador (`agente.py`) verificado con conversación real de 6 turnos.

**Pendiente de confirmación formal del usuario/equipo antes de considerar todo esto cerrado en el sentido estricto de `plan-de-fases.md`**, pero el criterio técnico de cada fase ya se cumplió.

## Decisiones tomadas

Una línea por decisión, el detalle va en `docs/DECISIONES.md` del repo.

- (vacío)

Decisiones que vienen dadas y no se rediscuten sin motivo nuevo:

- LangChain como framework base, requisito textual de la cátedra.
- PostgreSQL con pgvector como vector store, pedido explícito del profesor.
- Booking.com Demand API descartada por requerir aprobación de partner.
- Alcance acotado a 2 o 3 destinos piloto.
- Gemini con modelo Flash Lite y rotación de 3 claves. No se usa un modelo grande.
- Embeddings locales con sentence-transformers, para no gastar cuota de Gemini en embeber los corpus.
- Ningún commit lleva trailers de coautoría.
- Ningún workflow automático de CI consume cuota de LLM.

Decisiones tomadas en Fase 0:

- Postgres gestionado en Supabase como base compartida del equipo (D-02), `docker-compose.yml` se mantiene para desarrollo local y CI. **En la práctica se está trabajando contra el Postgres local de `docker-compose` mientras se resuelve Supabase con el equipo** — mismo esquema, mismo código, solo cambia `DATABASE_URL`.
- `GEMINI_MODEL=gemini-3.5-flash-lite`, confirmado contra la API real (D-03). `gemini-2.5-flash-lite` da 404 para estas cuentas.

Decisiones tomadas en Fase 1 (arranque):

- `cargar_vectores.py` se implementó contra la tabla propia (`documento_rag` de `sql/001_schema.sql`), no contra `langchain_postgres.PGVector`, para tener el pipeline de ingesta terminado de punta a punta sin esperar la decisión formal de Fase 2. Los retrievers de Fase 3 (`recuperacion/*.py`) siguen la misma consulta canónica sobre esa tabla. Migrar a `PGVector` sigue abierto si conviene (ver decisiones abiertas).
- "Europa" se resuelve a Barcelona, "Caribe" a Cancún / Riviera Maya (D-04), confirmado por el usuario.
- Amadeus dado de baja, migrado a RapidAPI/Booking.com15 (D-05/D-06). Booking.com15 sola cubre RF6 y RF7; Fly Scraper solo aporta `price-calendar` como dato complementario, el resto de sus endpoints no funciona.
- **RF4 (recomendación de comercios) movido de núcleo a extensión (D-07).** OpenTripMap no da volumen confiable de comercios sin curaduría manual de horas en ningún destino piloto. El núcleo de RAG queda en un solo corpus (atractivos), robusto y testeado, en vez de dos parciales. Código de RF4 ya escrito, no se borra.

## Decisiones abiertas

- **Fase 2:** `langchain_postgres.PGVector` contra tabla propia envuelta en un `BaseRetriever`. En la práctica ya se avanzó con la tabla propia (ver arriba) porque destrabó Fase 3 sin esperar; sigue abierto si el equipo prefiere migrar a `PGVector` antes de la defensa.
- **CrewAI:** sólo si el usuario trae confirmación explícita del profesor. Por defecto, no.

Decisiones tomadas en Fase 5:

- Orquestador implementado como una decisión de LLM con salida estructurada (mismo patrón que `completar_slots`), no como agente de tools de LangChain con `bind_tools` ni como grafo de LangGraph. Más simple de testear y de explicar en la defensa; se documenta como punto de partida, migrar a LangGraph si el flujo crece (arquitectura.md ya lo prevé).

## Bloqueos

- **Límite diario/por minuto real por clave de Gemini sigue sin poder verificarse de forma estática, y ya se sintió en la práctica (P-06 en DIFICULTADES.md).** El ID de modelo ya no es bloqueo (D-03). `ai.google.dev/gemini-api/docs/rate-limits` no publica un número fijo de RPD para el free tier, remite a `aistudio.google.com/rate-limit`, que requiere login con la cuenta de cada key. El 2026-09-11, tras varias decenas de llamadas reales acumuladas en la sesión, una invocación aislada tardó **42 segundos** (vs. 1-3s al arrancar la sesión), sin ningún error ni backoff logueado por el rotador — la demora viene de la API misma, probablemente cuota por minuto rozándose. **Alguien con acceso a esas cuentas de Google tiene que entrar logueado y anotar el RPD/RPM real por key.** Hasta entonces, dar por hecho que probar el sistema en vivo de forma intensiva (como para el video) puede degradar la latencia, y dejar colchón de tiempo.
- **Decisión pendiente con el equipo: seguir en Postgres local o migrar ya a Supabase.** Por ahora se está desarrollando y validando contra el Postgres local de `docker-compose` (ver Configuración del proyecto). Funciona igual de bien para seguir avanzando, pero antes de la entrega hay que decidir si el equipo se pasa a Supabase (para tener una base compartida) o se sigue en local hasta más adelante.
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados, requieren acceso al repo en GitHub.

## Próximo paso

1. ~~Decidir a qué ciudades puntuales se resuelven "Europa" y "Caribe"~~ — resuelto, Barcelona y Cancún/Riviera Maya (D-04).
2. ~~Verificar el model ID de Gemini~~ — resuelto contra la API real, `gemini-3.5-flash-lite` (D-03). El límite diario real por key sigue pendiente (ver bloqueo arriba).
3. ~~Levantar Postgres y aplicar el esquema~~ — resuelto en local con `docker-compose` + `inicializar_db`. Pendiente decidir Supabase con el equipo (ver bloqueo arriba).
4. ~~Ingestar Barcelona, Miami y Cancún contra OpenTripMap real~~ — hecho, ver tabla arriba (Fase 1). Aceptados los números reales tal como salieron, sin seguir ajustando parámetros de búsqueda (decisión del usuario).
4.b. ~~Decidir alcance de RF4/comercios~~ — resuelto, movido a extensión (D-07). Ya no bloquea Fase 1.
5. ~~Completar la curaduría manual de atractivos de Cancún~~ — resuelto, 13 lugares reales verificados en `data/curated/cancun_atractivos.json`. Cancún llega a 20/20.
6. ~~Cargar los vectores reales de los tres destinos~~ — resuelto, `scripts/cargar_destino.py` (nuevo) corrido contra Postgres local: Barcelona 43, Miami 77, Cancún 20 documentos en `documento_rag`. Retrieval semántico verificado a mano.
7. ~~Correr Fase 3, Fase 4, Fase 6 (armar_plan) y Fase 5 (orquestador) contra el corpus y el LLM reales~~ — resuelto, ver "Fase actual". Núcleo completo verificado de punta a punta con una conversación real de 6 turnos.
8. Cargar los repository secrets en GitHub y proteger `main` (checks `calidad`, `commits`, `secretos`).
9. Confirmar el cierre de núcleo con el usuario/equipo y mergear `fase/0-scaffolding` a `main`.
10. Con el núcleo cerrado, pasar a extensiones (Fase 7): RF9 (FAQ) primero, RF10 (gastos) después, y retomar RF4 (comercios) solo si queda tiempo (D-07).

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
