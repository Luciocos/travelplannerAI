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
| Destinos piloto | Europa, Miami, Caribe. **"Europa" y "Caribe" no son utilizables tal cual para la ingesta, ver bloqueos (D-04).** |
| LLM | Gemini, `gemini-2.5-flash-lite` por defecto vía `GEMINI_MODEL`. **ID y límite diario reales todavía sin verificar contra `ai.google.dev`, ver bloqueos.** |
| Claves de Gemini | 3, rotación round robin, cargadas en `.env` local por Lucio. Repository secrets de GitHub, pendientes de cargar. |
| Límite diario real por clave | (pendiente de verificar en la doc oficial, ver D-03 en DECISIONES.md) |
| Postgres | Supabase (ver D-02 en DECISIONES.md). `DATABASE_URL` pendiente de completar en `.env`. |

## Fase actual

**Código de las Fases 0, 1 y arranque de 2/3/4/8(RF8) escrito y con tests en verde, todo sin mergear a `main` y sin datos ni infraestructura real todavía.** El agente decidió avanzar código base en paralelo (autorizado explícitamente por el usuario, "seguí sin pedirme permiso") mientras las claves/infra que solo el usuario puede cargar se completaban. Nada de esto se corrió contra una API real ni una base real, y las fases no se consideran cerradas en el sentido del plan (`plan-de-fases.md`) hasta validarlas con datos e infraestructura reales y con confirmación del usuario.

- **Fase 0** (scaffolding): estructura del repo, hook de commits, workflows de CI, `docker-compose.yml`, `config.py`, rotador de claves con failover (`llm.py`), scripts de smoke test e inicialización de DB, esquema SQL, `docs/DECISIONES.md` / `docs/DIFICULTADES.md` armados.
- **Fase 1** (ingesta, sin datos reales): cliente de OpenTripMap en dos pasos, normalización (filtro 200 caracteres, separación atractivos/comercios), CLI `scripts/ingestar_destino.py`, `data/reference/paises.json`. **Bloqueada para generar datos reales por D-04 (ver abajo) y por falta de `OPENTRIPMAP_API_KEY`.**
- **Fase 2** (vector store, adelantada parcialmente): `embeddings.py` (sentence-transformers) y `db.py` + `ingesta/cargar_vectores.py` contra la tabla propia, sin correr contra Postgres real todavía.
- **Fase 3** (retrievers y tools de RAG, RF3/RF4): `recuperacion/atractivos.py`, `comercios.py`, `faq.py` con la consulta canónica (filtro + similitud en una sola query), y las tools `recomendar_actividades` / `recomendar_locales` con justificación por LLM solo sobre el texto recuperado. Verificado por test llamando las tools directo, sin agente, tal como pide el criterio de aceptación de esta fase — pero con retriever y LLM mockeados, no contra datos reales.
- **Fase 4** (estado y slot filling, RF1/RF2): `estado.py` (`PreferenciasViaje`, merge no destructivo, máximo 2 slots por turno) y la tool `completar_slots` con extracción estructurada. El caso de ejemplo de la consigna se cubre por test con el LLM mockeado.
- **RF8** (clima + idioma/moneda, de Fase 7, adelantado): `tools/info_destino.py`, clima en vivo de Open-Meteo (sin key) con el límite real de ~16 días manejado explícitamente, e idioma/moneda desde `data/reference/paises.json`.

39 tests en total (`pytest`), todos mockeados, ninguno toca la red ni una base real. Lint (`ruff`) en verde.

Todo en la rama `fase/0-scaffolding`, pusheada a origin, todavía no mergeada a `main`.

Falta para cerrar Fase 0 del todo: completar `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID/SECRET` y `DATABASE_URL` en `.env` (Gemini ya está cargado), verificar el modelo Gemini vigente, cargar los repository secrets, correr `smoke_llm.py` una vez a mano, y mergear a `main`.

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

- Postgres gestionado en Supabase como base compartida del equipo (D-02), `docker-compose.yml` se mantiene para desarrollo local y CI.
- `GEMINI_MODEL` queda por variable de entorno, sin hardcodear, hasta verificar el ID vigente (D-03).

Decisiones tomadas en Fase 1 (arranque):

- `cargar_vectores.py` se implementó contra la tabla propia (`documento_rag` de `sql/001_schema.sql`), no contra `langchain_postgres.PGVector`, para tener el pipeline de ingesta terminado de punta a punta sin esperar la decisión formal de Fase 2. Los retrievers de Fase 3 (`recuperacion/*.py`) siguen la misma consulta canónica sobre esa tabla. Migrar a `PGVector` sigue abierto si conviene (ver decisiones abiertas).

## Decisiones abiertas

- **Fase 2:** `langchain_postgres.PGVector` contra tabla propia envuelta en un `BaseRetriever`. En la práctica ya se avanzó con la tabla propia (ver arriba) porque destrabó Fase 3 sin esperar; sigue abierto si el equipo prefiere migrar a `PGVector` antes de la defensa.
- **Fase 5:** agente de tools plano contra LangGraph con nodos explícitos. Todavía no se escribió `agente.py`. Se decide cuando el flujo lo pida, no antes.
- **CrewAI:** sólo si el usuario trae confirmación explícita del profesor. Por defecto, no.

## Bloqueos

- **Model ID de Gemini Flash-Lite sin verificar contra la fuente oficial.** Una búsqueda rápida el 2026-09-10 mostró resultados de terceros inconsistentes entre sí (algunos ya hablan de generaciones "Gemini 3.x Flash-Lite", límites de RPD que van de ~20 a ~1000 según la fuente y el modelo). No se pudo confirmar limpio contra `ai.google.dev/gemini-api/docs/models` y `.../rate-limits`. Se dejó `gemini-2.5-flash-lite` como default configurable, sin cerrar la fase con ese dato como verificado. Alguien del equipo tiene que entrar a esas dos páginas, confirmar el ID y el límite diario real por clave, y actualizar `.env.example`, los cuatro workflows de `.github/workflows/` y esta tabla.
- `.env` local: faltan `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET` y `DATABASE_URL` (Gemini ya está).
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados, requieren acceso al repo en GitHub.
- **"Europa" y "Caribe" como destinos piloto no son coordenadas utilizables para OpenTripMap (D-04 en DECISIONES.md).** El equipo tiene que resolverlos a ciudades puntuales (ej. una capital europea, una ciudad caribeña) antes de poder correr `scripts/ingestar_destino.py` y curar `data/curated/` de verdad. Miami no tiene este problema.

## Próximo paso

1. **Decidir a qué ciudades puntuales se resuelven "Europa" y "Caribe"** (bloqueo nuevo de Fase 1, ver arriba). Sin esto no se puede generar el corpus real de esos dos destinos.
2. Verificar el model ID y el límite diario de Gemini Flash-Lite contra la doc oficial (ver bloqueo de arriba), actualizar donde corresponda.
3. Completar el resto de `.env` (OpenTripMap, Amadeus, DATABASE_URL de Supabase).
4. Cargar los repository secrets en GitHub y proteger `main` (checks `calidad`, `commits`, `secretos`).
5. Correr `python -m scripts.inicializar_db` contra Supabase y `python -m scripts.smoke_llm` una vez a mano.
6. Con las ciudades decididas y la API key cargada, correr `scripts/ingestar_destino.py` por destino y completar la curaduría manual en `data/curated/` para llegar al mínimo de 25 atractivos / 15 comercios por destino (criterio de aceptación de Fase 1).
7. Confirmar con el usuario y mergear `fase/0-scaffolding` a `main`.

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
