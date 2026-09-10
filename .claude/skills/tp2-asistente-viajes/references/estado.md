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
| Destinos piloto | Europa, Miami, Caribe |
| LLM | Gemini, `gemini-2.5-flash-lite` por defecto vía `GEMINI_MODEL`. **ID y límite diario reales todavía sin verificar contra `ai.google.dev`, ver bloqueos.** |
| Claves de Gemini | 3, rotación round robin, cargadas en `.env` local por Lucio. Repository secrets de GitHub, pendientes de cargar. |
| Límite diario real por clave | (pendiente de verificar en la doc oficial, ver D-03 en DECISIONES.md) |
| Postgres | Supabase (ver D-02 en DECISIONES.md). `DATABASE_URL` pendiente de completar en `.env`. |

## Fase actual

**Fase 0, scaffolding.** Estructura del repo, hook de commits, workflows de CI, `docker-compose.yml`, `config.py`, rotador de claves (`llm.py`), scripts de smoke test e inicialización de DB, esquema SQL, y `docs/DECISIONES.md` / `docs/DIFICULTADES.md` armados. Trabajo hecho en la rama `fase/0-scaffolding`, todavía no mergeada a `main` (falta confirmación del usuario y cargar los secrets/proteger `main` en GitHub).

Falta para cerrar la fase del todo: completar `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID/SECRET` y `DATABASE_URL` en `.env` (Gemini ya está cargado), verificar el modelo Gemini vigente, cargar los repository secrets, correr `smoke_llm.py` una vez a mano, y mergear a `main`.

## Fases cerradas

(ninguna, Fase 0 en curso)

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

## Decisiones abiertas

- **Fase 2:** `langchain_postgres.PGVector` contra tabla propia envuelta en un `BaseRetriever`. Default recomendado, `PGVector`.
- **Fase 5:** agente de tools plano contra LangGraph con nodos explícitos. Se decide cuando el flujo lo pida, no antes.
- **CrewAI:** sólo si el usuario trae confirmación explícita del profesor. Por defecto, no.

## Bloqueos

- **Model ID de Gemini Flash-Lite sin verificar contra la fuente oficial.** Una búsqueda rápida el 2026-09-10 mostró resultados de terceros inconsistentes entre sí (algunos ya hablan de generaciones "Gemini 3.x Flash-Lite", límites de RPD que van de ~20 a ~1000 según la fuente y el modelo). No se pudo confirmar limpio contra `ai.google.dev/gemini-api/docs/models` y `.../rate-limits`. Se dejó `gemini-2.5-flash-lite` como default configurable, sin cerrar la fase con ese dato como verificado. Alguien del equipo tiene que entrar a esas dos páginas, confirmar el ID y el límite diario real por clave, y actualizar `.env.example`, los cuatro workflows de `.github/workflows/` y esta tabla.
- `.env` local: faltan `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET` y `DATABASE_URL` (Gemini ya está).
- Repository secrets de GitHub (`GEMINI_API_KEY_1/2/3`) y protección de la rama `main` todavía no configurados, requieren acceso al repo en GitHub.

## Próximo paso

1. Verificar el model ID y el límite diario de Gemini Flash-Lite contra la doc oficial (ver bloqueo de arriba), actualizar donde corresponda.
2. Completar el resto de `.env` (OpenTripMap, Amadeus, DATABASE_URL de Supabase).
3. Cargar los repository secrets en GitHub y proteger `main` (checks `calidad`, `commits`, `secretos`).
4. Correr `python -m scripts.inicializar_db` contra Supabase y `python -m scripts.smoke_llm` una vez a mano.
5. Confirmar con el usuario y mergear `fase/0-scaffolding` a `main`, luego arrancar Fase 1 (ingesta).

---

## Cómo actualizar este archivo

Al cerrar una fase, tocar exactamente esto:

1. Fecha de última actualización.
2. Mover la fase de "actual" a "cerradas", con una línea de qué quedó funcionando.
3. Agregar las decisiones nuevas, una línea cada una, y sacarlas de "abiertas" si estaban ahí.
4. Actualizar bloqueos y próximo paso.

No convertir esto en un diario. Es un estado, no un historial. Lo que importa es que alguien que abre el proyecto sin contexto sepa en 30 segundos dónde está parado.
