# travelplannerAI

Sistema experto conversacional de planificación de viajes (TP2, Inteligencia Artificial, UTN FRRo). El usuario describe en lenguaje natural qué viaje busca, el agente completa por preguntas lo que falta, recomienda actividades y locales vía RAG, arma un itinerario día a día con costo estimado, y responde consultas puntuales sobre el destino.

Construido con **LangChain** (LangGraph si el flujo lo pide) y **PostgreSQL + pgvector** como vector store. Destinos piloto: Europa, Miami, Caribe.

El entregable oficial de la cátedra es el notebook `notebooks/demo_tp2.ipynb`. Toda la lógica de negocio vive en `src/asistente_viajes/`, el notebook solo importa y ejecuta.

## Estado del proyecto

Ver `.claude/skills/tp2-asistente-viajes/references/estado.md` (archivo vivo, fase actual y bloqueos) y `docs/PROGRESO.md` (resumen para el equipo de qué está hecho y qué falta).

## Instalación

Requiere Python 3.11+.

```bash
git clone https://github.com/Luciocos/travelplannerAI.git
cd travelplannerAI
git config core.hooksPath .githooks   # activa el hook que bloquea commits mal formados

python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                  # completar las variables, ver abajo
```

### Variables de entorno (`.env`)

| Variable | Qué es |
|----------|--------|
| `LLM_PROVIDER` | `gemini` |
| `GEMINI_MODEL` | ID del modelo Flash-Lite vigente (verificar en `ai.google.dev`) |
| `GEMINI_API_KEY_1` / `_2` / `_3` | Claves de Gemini, rotación round robin |
| `OPENTRIPMAP_API_KEY` | Clave de OpenTripMap (ingesta de POIs) |
| `RAPIDAPI_KEY` / `RAPIDAPI_HOST_BOOKING` / `RAPIDAPI_HOST_FLY_SCRAPER` | Extensiones de alojamiento y vuelos, Booking.com15 (reemplaza a Amadeus, dado de baja en 2026, ver D-06 en DECISIONES.md) |
| `DATABASE_URL` | Connection string de Postgres (Supabase, o local vía `docker-compose`) |

**Nunca** se versionan valores reales, solo nombres. `.env` está en `.gitignore`.

### Base de datos

Opción A, local con Docker:

```bash
docker compose up -d
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/asistente_viajes
```

Opción B, Supabase (base compartida del equipo, ver `docs/DECISIONES.md` D-02): usar la connection string del panel del proyecto.

En cualquiera de los dos casos, aplicar el esquema:

```bash
python -m scripts.inicializar_db
```

### Verificar que todo arranca

```bash
python -c "from asistente_viajes import config"   # no debe romper
pytest                                              # tests que no tocan la red
python -m scripts.smoke_llm                         # a mano, consume cuota real de las 3 claves
```

## Arquitectura

Ver `.claude/skills/tp2-asistente-viajes/references/arquitectura.md` para la estructura completa del repo, el esquema SQL, el patrón de consulta de pgvector y los contratos de las tools.

Mapa rápido de requerimiento funcional a tool a archivo, en `.claude/skills/tp2-asistente-viajes/SKILL.md`.

## Convenciones de trabajo

- Commits en español, formato `tipo(alcance): descripción`, sin trailers de coautoría (hook local + CI lo hacen cumplir). Detalle en `.claude/skills/tp2-asistente-viajes/references/ci-y-git.md`.
- Una rama por fase (`fase/N-nombre`), merge a `main` con el CI en verde. No commitear directo a `main`.
- Documentación de decisiones y dificultades en `docs/DECISIONES.md` y `docs/DIFICULTADES.md`, insumo directo de la defensa oral.

## Equipo

Lucio Cosentino, Joaquin Carlos Fernandez Da Silva, Aaron de Bernardo, Elias Danteo.
