# Progreso del proyecto

Resumen para el equipo de qué está hecho y qué falta. Es el punto de entrada rápido para quien retoma el trabajo. El detalle técnico vivo está en `.claude/skills/tp2-asistente-viajes/references/estado.md`; este archivo es la versión legible para todo el equipo, no solo para quien usa la skill.

Última actualización: 2026-09-10, por Lucio.

---

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

Todo esto vive en la rama `fase/0-scaffolding`, **todavía no mergeado a `main`**.

## Falta para cerrar la Fase 0

1. **Verificar el model ID de Gemini Flash-Lite vigente y su límite diario real** contra `https://ai.google.dev/gemini-api/docs/models` y `.../rate-limits`. Una búsqueda rápida dio resultados de terceros inconsistentes (algunos ya mencionan generaciones "Gemini 3.x"), así que quedó `gemini-2.5-flash-lite` como default sin confirmar. Actualizar `.env.example`, los 4 workflows y `estado.md` con el valor verificado.
2. Completar en `.env` (ya cargado: las 3 claves de Gemini): `OPENTRIPMAP_API_KEY`, `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, `DATABASE_URL`.
3. Cargar `GEMINI_API_KEY_1/2/3` como **repository secrets** en GitHub (Settings → Secrets and variables → Actions).
4. Proteger la rama `main` en GitHub: requerir PR, y los checks `calidad`, `commits`, `secretos` en verde antes de mergear.
5. Correr `python -m scripts.inicializar_db` contra la base elegida (Supabase) y `python -m scripts.smoke_llm` una vez a mano, para confirmar que la rotación de claves funciona de punta a punta.
6. Mergear `fase/0-scaffolding` a `main` con el CI en verde.

## No arrancar todavía

Fases 1 a 9 (ingesta de datos, vector store, retrievers, slot filling, orquestador, `armar_plan`, extensiones, notebook, documentación final). El detalle de cada una, con criterios de aceptación, está en `.claude/skills/tp2-asistente-viajes/references/plan-de-fases.md`. **No se avanza a la Fase 1 sin que el dueño del proyecto lo confirme.**

## Cómo retomar

1. Leer `.claude/skills/tp2-asistente-viajes/references/estado.md` (fase actual, bloqueos, próximo paso).
2. Leer este archivo.
3. Si algo de acá quedó viejo porque alguien ya lo resolvió, actualizarlo al cerrar esa unidad de trabajo, no dejarlo desactualizado para la próxima persona.
