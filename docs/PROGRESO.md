# Progreso del proyecto

Resumen para el equipo de qué está hecho y qué falta. Es el punto de entrada rápido para quien retoma el trabajo. El detalle técnico vivo está en `.claude/skills/tp2-asistente-viajes/references/estado.md`; este archivo es la versión legible para todo el equipo, no solo para quien usa la skill.

Última actualización: 2026-09-10, por Lucio.

---

## ⚠️ Bloqueo que el equipo tiene que resolver, no es técnico

Los destinos piloto que trae la consigna del equipo son "Europa, Miami, Caribe". **Miami sirve tal cual, pero "Europa" y "Caribe" no**: la fuente de datos (OpenTripMap) busca alrededor de una coordenada puntual, no de un continente ni de una región. Hay que decidir a qué ciudad puntual se reduce cada uno (por ejemplo, una capital europea y una ciudad caribeña) antes de poder generar los corpus de esos dos destinos. Ver `docs/DECISIONES.md` (D-04) y `docs/DIFICULTADES.md` (P-01) para el detalle. El código de ingesta ya está listo y funciona con cualquier ciudad que se elija, no hace falta tocarlo.

## Hecho (Fase 0, scaffolding)

- Estructura completa del repo (`src/asistente_viajes/`, `sql/`, `data/`, `scripts/`, `tests/`, `docs/`).
- `.githooks/commit-msg`: bloquea commits con trailer `Co-Authored-By` o mención a la herramienta generadora, y valida el formato `tipo(alcance): descripción`. Activado con `git config core.hooksPath .githooks` (correrlo en cada clon nuevo).
- Cuatro workflows de CI en `.github/workflows/`: `ci.yml` (lint + tests + Postgres/pgvector de servicio), `commits.yml` (valida mensajes en cada PR), `secretos.yml` (gitleaks + guard de claves de Gemini), `smoke-llm.yml` (manual, único que consume cuota real).
- `docker-compose.yml` con `pgvector/pgvector:pg16`, para desarrollo local o CI.
- `requirements.txt` con las dependencias acordadas (LangChain, langchain-postgres, langchain-google-genai, sentence-transformers, psycopg, pgvector, pydantic, etc.).
- `.env.example` con todos los nombres de variable (sin valores).
- `sql/001_schema.sql`: tabla `documento_rag` (los tres corpus de RAG) con índices de filtro y HNSW coseno, más `itinerario`, `itinerario_item`, `participante`, `gasto` para las fases siguientes.
- `src/asistente_viajes/config.py`: carga `.env`, arma la lista de claves de Gemini dinámicamente (`GEMINI_API_KEY_<n>`), falla rápido y claro si falta algo. Con test (`tests/test_config.py`, 3 casos, pasan).
- `src/asistente_viajes/llm.py`: rotador round robin de claves de Gemini, distingue límite por minuto (backoff 60s) de límite diario (clave muerta hasta el reset), logging por índice de clave (nunca el valor).
- `scripts/smoke_llm.py`: prueba la rotación contra la API real, a correr a mano (consume cuota).
- `scripts/inicializar_db.py`: aplica `sql/001_schema.sql` contra `DATABASE_URL`.
- `docs/DECISIONES.md` y `docs/DIFICULTADES.md`, copiados de la plantilla de la skill, con las primeras tres decisiones cargadas (pgvector vs Chroma, Supabase como base compartida, model ID de Gemini pendiente de verificar).
- `README.md` con instalación, variables de entorno y cómo levantar la base.
- Lint (`ruff check`) y tests (`pytest`) corren en verde en local.
- Hook de commits verificado: rechaza un mensaje con trailer `Co-Authored-By` (probado a mano).

Todo esto vive en la rama `fase/0-scaffolding` (pusheada a GitHub), **todavía no mergeada a `main`**.

## Hecho (Fase 1, ingesta, arrancada en paralelo, sin datos reales todavía)

- `src/asistente_viajes/ingesta/opentripmap.py`: cliente de los dos pasos (búsqueda por radio + detalle por `xid`), guarda crudo en `data/raw/` antes de normalizar, sigue funcionando desde el cache si la API cae.
- `src/asistente_viajes/ingesta/normalizar.py`: filtra POIs con menos de 200 caracteres de texto real, separa en corpus `atractivos` / `comercios` según `kind`, y normaliza también los registros curados a mano.
- `src/asistente_viajes/embeddings.py`: wrapper de `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim, normalizado).
- `src/asistente_viajes/db.py` y `src/asistente_viajes/ingesta/cargar_vectores.py`: conexión a Postgres y upsert en `documento_rag` con embedding, implementado contra la tabla propia del esquema (ver decisión D-04 de `arquitectura.md` sobre PGVector vs tabla propia, sigue abierta pero esto ya funciona).
- `scripts/ingestar_destino.py`: CLI, `python -m scripts.ingestar_destino --destino <nombre> --lat <lat> --lon <lon>`.
- `data/reference/paises.json`: idioma y moneda de los países más probables (para RF8 en Fase 7), a completar cuando se definan las ciudades finales.
- 12 tests en total (`pytest`), todos mockeados, ninguno toca la red ni Postgres real.

**No se corrió contra la API real, no hay datos cargados todavía.** Falta `OPENTRIPMAP_API_KEY` en `.env` y, sobre todo, resolver el bloqueo de destinos de arriba.

## Hecho (Fase 2/3/4 y RF8, adelantadas en código mientras se esperaban las claves)

El agente siguió escribiendo código base mientras faltaban `.env` y accesos, sin datos ni infraestructura real todavía detrás. Nada de esto está "cerrado" en el sentido del plan de fases, pero el código y los tests están listos:

- **Fase 2 (vector store):** `src/asistente_viajes/embeddings.py` (modelo local de embeddings) y `db.py` (conexión a Postgres), usados por `cargar_vectores.py` de Fase 1.
- **Fase 3 (retrievers y tools de RAG, RF3/RF4):** `src/asistente_viajes/recuperacion/{atractivos,comercios,faq}.py` con la consulta canónica (filtro por destino + similitud semántica en una sola query SQL). Tools `recomendar_actividades` y `recomendar_locales` en `src/asistente_viajes/tools/`, con `args_schema` y docstring para que el agente las entienda, y justificación generada por LLM **solo** a partir del texto recuperado.
- **Fase 4 (estado y slot filling, RF1/RF2):** `src/asistente_viajes/estado.py` (`PreferenciasViaje`, merge no destructivo — nunca pisa un slot ya cargado) y la tool `completar_slots` en `src/asistente_viajes/tools/`, que pregunta como máximo 2 datos faltantes por turno.
- **RF8 (de Fase 7, adelantado porque no depende de ninguna clave):** `tools/info_destino.py`, clima en vivo de Open-Meteo (sin API key) con el límite real de ~16 días manejado explícitamente (nunca inventa un pronóstico para fechas lejanas), e idioma/moneda desde `data/reference/paises.json`.

39 tests en total, todos con mocks (LLM, Postgres, HTTP), ninguno toca la red ni una base real. Lint en verde.

**Lo que falta para que esto sea real y no solo código:** correr todo contra una base Postgres real con datos cargados (bloqueado por lo de arriba) y contra el LLM real (bloqueado por el model ID sin verificar). Todavía no existe `agente.py` (el orquestador de Fase 5) ni `armar_plan` (Fase 6), esos sí no se tocaron.

## Falta para cerrar la Fase 0

1. **Verificar el model ID de Gemini Flash-Lite vigente y su límite diario real** contra `https://ai.google.dev/gemini-api/docs/models` y `.../rate-limits`. Una búsqueda rápida dio resultados de terceros inconsistentes (algunos ya mencionan generaciones "Gemini 3.x"), así que quedó `gemini-2.5-flash-lite` como default sin confirmar. Actualizar `.env.example`, los 4 workflows y `estado.md` con el valor verificado.
2. Completar en `.env` (ya cargado: las 3 claves de Gemini): `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, `DATABASE_URL`.
3. Cargar `GEMINI_API_KEY_1/2/3` como **repository secrets** en GitHub (Settings → Secrets and variables → Actions).
4. Proteger la rama `main` en GitHub: requerir PR, y los checks `calidad`, `commits`, `secretos` en verde antes de mergear.
5. Correr `python -m scripts.inicializar_db` contra la base elegida (Supabase) y `python -m scripts.smoke_llm` una vez a mano, para confirmar que la rotación de claves funciona de punta a punta.
6. Mergear `fase/0-scaffolding` a `main` con el CI en verde.

## Falta para cerrar la Fase 1

1. Resolver el bloqueo de destinos (arriba).
2. Completar `OPENTRIPMAP_API_KEY` en `.env`.
3. Correr `python -m scripts.ingestar_destino` para cada destino ya con coordenadas concretas.
4. Curar a mano en `data/curated/` los lugares importantes que la API no cubra bien (ej. mercados artesanales), marcados con `fuente='curado'`.
5. Llegar al mínimo de 25 documentos de atractivos y 15 de comercios por destino, todos con texto real (criterio de aceptación de Fase 1 en `plan-de-fases.md`).

## No arrancar todavía

`agente.py` (orquestador, Fase 5), `armar_plan` (Fase 6), y el resto de las extensiones (RF6/RF7 alojamiento y vuelos, RF9 FAQ, RF10 gastos), más el notebook de demo y la documentación final (Fases 8 y 9). El detalle de cada una, con criterios de aceptación, está en `.claude/skills/tp2-asistente-viajes/references/plan-de-fases.md`. **No se avanza de fase sin que el dueño del proyecto lo confirme**, salvo el trabajo de código base que no depende de una decisión de producto ni de credenciales, que se adelantó para no perder tiempo de sesión (ver arriba).

## Cómo retomar

1. Leer `.claude/skills/tp2-asistente-viajes/references/estado.md` (fase actual, bloqueos, próximo paso).
2. Leer este archivo.
3. Si algo de acá quedó viejo porque alguien ya lo resolvió, actualizarlo al cerrar esa unidad de trabajo, no dejarlo desactualizado para la próxima persona.
