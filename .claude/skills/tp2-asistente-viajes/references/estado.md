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

**Código de las Fases 0 a 4 y de RF6/RF7/RF8 (Fase 7) escrito, con tests en verde y ya validado con infraestructura y APIs reales (local, no Supabase todavía).** Sigue sin mergear a `main` ni confirmarse como cerrado en el sentido de `plan-de-fases.md`, pero a diferencia del corte anterior, buena parte de esto ya corrió de verdad: Postgres local, OpenTripMap, Gemini y Booking.com15 reales, no solo mocks.

- **Fase 0** (scaffolding): estructura del repo, hook de commits, workflows de CI, `config.py`, rotador de claves con failover (`llm.py`), esquema SQL. **`docker-compose up -d` levantado y funcionando**, esquema aplicado con `inicializar_db` contra esa base local, `smoke_llm.py` corrido a mano: **5/5 claves responden `200 OK`** con `gemini-3.5-flash-lite` (ver D-03).
- **Fase 1** (ingesta): cliente de OpenTripMap en dos pasos, normalización, CLI `scripts/ingestar_destino.py` (con `--rate`/`--limite` nuevos, ver abajo). **Corrida real completa para los tres destinos piloto:**

  | Destino | Atractivos (min. 25) | Comercios (min. 15) |
  |---|---|---|
  | Barcelona | 41 ✅ | 2 |
  | Miami | 75 ✅ | 2 |
  | Cancún | 7 (con `--rate 1 --radio 50000 --limite 500`) | 0 |

  **Comercios queda sistemáticamente por debajo del mínimo en los tres destinos** (no es un caso aislado de Cancún): OpenTripMap casi no tiene locales/gastronomía con extracto de Wikipedia, es lo que anticipaba `fuentes-datos.md`. Cancún además queda corto en atractivos (7 de 25) por baja densidad de contenido editorial en esa zona, incluso relajando el filtro de significancia (`rate`) y ampliando radio a 50km — probado y descartado seguir ajustando parámetros (decisión explícita del usuario: aceptar que hay pocos lugares registrados y resolver por curaduría manual antes de invertir más tiempo en tuning). **Falta curaduría manual en `data/curated/` para los tres destinos, con foco fuerte en comercios y en atractivos de Cancún, para cerrar el criterio de aceptación de la fase.**
- **Fase 2** (vector store): `embeddings.py` + `db.py` + `ingesta/cargar_vectores.py` contra la tabla propia. Escrito, todavía no se corrió la carga real de vectores (viene después de completar la curaduría de Fase 1).
- **Fase 3** (retrievers y tools de RAG, RF3/RF4): `recuperacion/*.py` + `recomendar_actividades`/`recomendar_locales`. Verificado por test con retriever y LLM mockeados, sin agente, sin corpus real todavía (depende de Fase 2).
- **Fase 4** (estado y slot filling, RF1/RF2): `estado.py` + `completar_slots`. Test con LLM mockeado.
- **RF8** (clima + idioma/moneda): `tools/info_destino.py`, clima en vivo de Open-Meteo, idioma/moneda desde `paises.json`.
- **RF6/RF7** (alojamiento y vuelos): Amadeus dado de baja, migrado a RapidAPI/Booking.com15 (D-05/D-06). `services/rapidapi/` + tools `buscar_alojamiento`/`buscar_vuelos`. **Verificado de punta a punta contra la base local y la API real**: destinos piloto precargados en `destino_externo` (Barcelona/Cancún para hoteles, Buenos Aires/Cancún para vuelos), `buscar_alojamiento("Barcelona", ...)` corrido de verdad devolvió 20 hoteles reales usando el cache (sin re-resolver destino). Fly Scraper reducido a `price-calendar` como dato complementario.

69 tests unitarios (`pytest`) mockeados y en verde, más las verificaciones manuales reales de arriba. Lint (`ruff`) en verde. Venv local (`.venv`) armado porque esta máquina no tenía dependencias instaladas.

Todo en la rama `fase/0-scaffolding`, pusheada a origin, todavía no mergeada a `main`.

Falta para cerrar Fase 0 del todo: decidir con el equipo si se pasa a Supabase o se sigue en local por ahora, cargar los repository secrets de GitHub, y mergear a `main`.

## Fases cerradas

(ninguna todavía formalmente — hay código y tests en verde de varias fases, pero cerrar una fase requiere el criterio de aceptación real con datos e infraestructura, mas confirmación del usuario, ver arriba)

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

## Decisiones abiertas

- **Fase 2:** `langchain_postgres.PGVector` contra tabla propia envuelta en un `BaseRetriever`. En la práctica ya se avanzó con la tabla propia (ver arriba) porque destrabó Fase 3 sin esperar; sigue abierto si el equipo prefiere migrar a `PGVector` antes de la defensa.
- **Fase 5:** agente de tools plano contra LangGraph con nodos explícitos. Todavía no se escribió `agente.py`. Se decide cuando el flujo lo pida, no antes.
- **CrewAI:** sólo si el usuario trae confirmación explícita del profesor. Por defecto, no.

## Bloqueos

- **Límite diario real por clave de Gemini sigue sin poder verificarse de forma estática.** El ID de modelo ya no es bloqueo (D-03). `ai.google.dev/gemini-api/docs/rate-limits` no publica un número fijo de RPD para el free tier, remite a `aistudio.google.com/rate-limit`, que requiere login con la cuenta de cada key. Hay reportes de foro (no oficiales) de recortes recientes al free tier. **Alguien con acceso a esas cuentas de Google tiene que entrar logueado y anotar el RPD real por key.**
- **Decisión pendiente con el equipo: seguir en Postgres local o migrar ya a Supabase.** Por ahora se está desarrollando y validando contra el Postgres local de `docker-compose` (ver Configuración del proyecto). Funciona igual de bien para seguir avanzando, pero antes de la entrega hay que decidir si el equipo se pasa a Supabase (para tener una base compartida) o se sigue en local hasta más adelante.
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados, requieren acceso al repo en GitHub.
- **Corpus por debajo del mínimo con solo la API, los tres destinos.** Comercios: 2/2/0 (Barcelona/Miami/Cancún) contra el mínimo de 15 — esperado, casi ningún local tiene extracto de Wikipedia. Atractivos: Cancún da solo 7 de 25 incluso con `--rate 1 --radio 50000 --limite 500` (probado y no se sigue ajustando, decisión del usuario). **Hace falta curaduría manual en `data/curated/` para los tres destinos, marcado `fuente='curado'`, antes de cerrar Fase 1** — es el bloqueo real que sigue, no algo que un parámetro de API vaya a resolver.

## Próximo paso

1. ~~Decidir a qué ciudades puntuales se resuelven "Europa" y "Caribe"~~ — resuelto, Barcelona y Cancún/Riviera Maya (D-04).
2. ~~Verificar el model ID de Gemini~~ — resuelto contra la API real, `gemini-3.5-flash-lite` (D-03). El límite diario real por key sigue pendiente (ver bloqueo arriba).
3. ~~Levantar Postgres y aplicar el esquema~~ — resuelto en local con `docker-compose` + `inicializar_db`. Pendiente decidir Supabase con el equipo (ver bloqueo arriba).
4. ~~Ingestar Barcelona, Miami y Cancún contra OpenTripMap real~~ — hecho, ver tabla arriba (Fase 1). Aceptados los números reales tal como salieron, sin seguir ajustando parámetros de búsqueda (decisión del usuario).
5. **Completar la curaduría manual en `data/curated/`** para los tres destinos (bloqueo de arriba) — es lo que falta para cerrar el criterio de aceptación de Fase 1. Foco: comercios en los tres, atractivos en Cancún.
6. Cargar los vectores reales (Fase 2, `cargar_vectores.py`) una vez cerrada la curaduría, y correr Fase 3 (RAG) y Fase 4 (slot filling) contra datos reales en vez de mocks.
7. Cargar los repository secrets en GitHub y proteger `main` (checks `calidad`, `commits`, `secretos`).
8. Confirmar con el usuario y mergear `fase/0-scaffolding` a `main`.

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
