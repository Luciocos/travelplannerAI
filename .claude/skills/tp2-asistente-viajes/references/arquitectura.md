# Arquitectura

## Estructura del repo

```
<repo>/
├── README.md
├── .github/workflows/            # ci.yml, commits.yml, secretos.yml, smoke-llm.yml
├── .githooks/commit-msg          # bloquea trailers de coautoria y formato invalido
├── .claude/skills/tp2-asistente-viajes/   # esta skill, versionada con el repo
├── .env.example
├── .gitignore
├── requirements.txt
├── docker-compose.yml            # postgres 16 con pgvector, para local
├── docs/
│   ├── DECISIONES.md             # log de decisiones tecnicas, insumo de la defensa
│   └── DIFICULTADES.md           # problemas encontrados y como se resolvieron
├── sql/
│   └── 001_schema.sql
├── data/
│   ├── raw/                      # respuestas crudas de OpenTripMap por destino (json)
│   ├── curated/                  # POIs y comercios completados a mano
│   └── reference/paises.json     # pais -> idioma oficial -> moneda
├── src/asistente_viajes/
│   ├── config.py                 # carga de .env, constantes, destinos habilitados
│   ├── llm.py                    # factory del ChatModel mas rotador de claves
│   ├── embeddings.py             # modelo de embeddings, dimension, normalizacion
│   ├── db.py                     # conexion y helpers de Postgres
│   ├── prompts.py                # todos los prompts, como constantes con nombre
│   ├── estado.py                 # PreferenciasViaje (pydantic), slots y validacion
│   ├── ingesta/
│   │   ├── opentripmap.py        # cliente de la API, dos pasos
│   │   ├── normalizar.py         # POI crudo -> documento de corpus
│   │   └── cargar_vectores.py    # embebido y upsert en pgvector
│   ├── recuperacion/
│   │   ├── atractivos.py
│   │   ├── comercios.py
│   │   └── faq.py
│   ├── services/
│   │   └── rapidapi/          # RF6/RF7, reemplaza a Amadeus (D-06)
│   │       ├── client.py      # headers, retry, timeout, contador de cuota
│   │       ├── models.py      # DestinoResuelto, Alojamiento, OpcionVuelo
│   │       ├── booking.py     # adaptador Booking.com15 (hoteles)
│   │       ├── fly_scraper.py # adaptador Fly Scraper (vuelos)
│   │       ├── cache.py       # cache de resolucion de destinos en Postgres
│   │       └── fixtures/      # respuestas reales grabadas, una por endpoint
│   ├── tools/
│   │   ├── completar_slots.py
│   │   ├── recomendar_actividades.py
│   │   ├── recomendar_locales.py
│   │   ├── armar_plan.py
│   │   ├── info_destino.py       # clima mas idioma y moneda
│   │   ├── buscar_alojamiento.py # RF6, sobre services/rapidapi (booking + fallback fly_scraper)
│   │   ├── buscar_vuelos.py      # RF7, sobre services/rapidapi (fly_scraper + fallback booking)
│   │   └── gastos.py
│   └── agente.py                 # orquestador, memoria, registro de tools
├── notebooks/
│   └── demo_tp2.ipynb            # ENTREGABLE OFICIAL
├── scripts/
│   ├── ingestar_destino.py       # CLI: python -m scripts.ingestar_destino --destino Salta
│   ├── inicializar_db.py
│   └── smoke_llm.py              # verifica la rotacion de claves contra la API
└── tests/
```

## Dependencias

`langchain`, `langchain-core`, `langchain-community`, `langchain-postgres`, `langchain-google-genai`, `sentence-transformers`, `psycopg[binary]`, `pgvector`, `pydantic`, `python-dotenv`, `httpx`, `jupyter`, `pytest`, `pytest-mock`, `ruff` (sólo desarrollo).

Cualquier dependencia fuera de esta lista se justifica antes de agregarla.

## Variables de entorno

`LLM_PROVIDER`, `GEMINI_MODEL`, `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`, `OPENTRIPMAP_API_KEY`, `RAPIDAPI_KEY`, `RAPIDAPI_HOST_BOOKING`, `RAPIDAPI_HOST_FLY_SCRAPER`, `RAPIDAPI_MONTHLY_QUOTA_BOOKING`, `RAPIDAPI_MONTHLY_QUOTA_FLY_SCRAPER`, `USE_FIXTURES`, `DATABASE_URL`. Amadeus se dio de baja (D-05/D-06 en `docs/DECISIONES.md`), RF6/RF7 corren sobre RapidAPI (Booking.com15 + Fly Scraper).

`config.py` falla rápido y con mensaje claro si falta una variable requerida, y levanta todas las variables que matcheen `GEMINI_API_KEY_\d+` en una lista, sin cantidad hardcodeada. Ver `llm-y-claves.md`.

## Vector store

Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensiones, multilingüe, corre en CPU sin GPU. Vectores normalizados, distancia coseno.

Nota sobre operadores de pgvector, para no equivocarse: `<->` es L2, `<=>` es coseno, `<#>` es producto interno negativo. Con vectores normalizados L2 y coseno ordenan igual, pero se usa `<=>` por convención y para que el índice `vector_cosine_ops` sea el correcto.

### Esquema base

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documento_rag (
    id            BIGSERIAL PRIMARY KEY,
    corpus        TEXT NOT NULL CHECK (corpus IN ('atractivos', 'comercios', 'faq')),
    destino       TEXT NOT NULL,
    nombre        TEXT,
    categoria     TEXT,
    texto         TEXT NOT NULL,
    direccion     TEXT,
    rango_precio  TEXT,
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    fuente        TEXT NOT NULL,          -- 'opentripmap' | 'curado'
    xid           TEXT UNIQUE,
    embedding     VECTOR(384) NOT NULL
);

CREATE INDEX idx_documento_rag_filtro ON documento_rag (corpus, destino);
CREATE INDEX idx_documento_rag_emb ON documento_rag
    USING hnsw (embedding vector_cosine_ops);
```

### Consulta canónica

```sql
SELECT nombre, categoria, texto, direccion, rango_precio
FROM documento_rag
WHERE corpus = %(corpus)s AND destino = %(destino)s
ORDER BY embedding <=> %(consulta)s::vector
LIMIT %(k)s;
```

Filtro por metadata y búsqueda semántica en **una sola consulta**. Ese es el argumento concreto a favor de pgvector frente a Chroma, y hay que poder decirlo así en la defensa. Segundo argumento: las tablas estructuradas (itinerarios, gastos) viven en la misma base que los vectores, un solo motor en vez de dos.

### Decisión abierta, resolver en Fase 2

Dos caminos, los dos válidos y los dos 100% LangChain:

- **`langchain_postgres.PGVector`**: integración oficial, metadata en jsonb, mucho menos código propio. Default recomendado para los tres corpus.
- **Tabla propia** (la de arriba) envuelta en un `BaseRetriever` de LangChain: control total del SQL, más fácil de mostrar en la defensa.

En cualquiera de los dos casos, las tablas de itinerarios y gastos son propias y viven en la misma base. Si aparece fricción con el filtrado por metadata de `PGVector`, migrar a la tabla propia y documentarlo como decisión con su motivo.

## Modelo de estado

`PreferenciasViaje`, pydantic, todos los campos opcionales:

`destino`, `tipo_destino`, `intereses: list[str]`, `presupuesto`, `fecha_inicio`, `fecha_fin`, `cantidad_personas`.

Reglas de merge, esto es RF2 y es donde se rompe siempre:

- El merge es **no destructivo**: un slot ya cargado nunca se pisa con `None`.
- Nunca repreguntar algo que ya está en el estado.
- Máximo 2 slots faltantes por turno, para que la conversación no parezca un formulario.

## Contratos de las tools

Todas son `@tool` de LangChain, con `args_schema` de pydantic y docstring precisa.

- `completar_slots(mensaje: str, estado_actual: PreferenciasViaje) -> tuple[PreferenciasViaje, str | None]`. Extracción estructurada con `with_structured_output` del ChatModel, merge no destructivo, y pregunta por lo que falta (o `None` si está completo).
- `recomendar_actividades(destino: str, intereses: list[str], k: int = 5)`. Devuelve nombre, categoría y una línea de justificación generada por el LLM **sólo** sobre el texto recuperado, con instrucción explícita de no agregar datos.
- `recomendar_locales(destino: str, consulta: str, k: int = 5)`. Mismo patrón sobre el corpus de comercios, devuelve dirección y rango de precio.
- `armar_plan(estado: PreferenciasViaje)`. Itinerario día a día, 2 o 3 actividades por día, costo estimado y resumen de presupuesto. Persiste en `itinerario` e `itinerario_item`.
- `info_destino(destino: str, fecha_inicio, fecha_fin)`. Clima en vivo mas idioma y moneda. Se dispara automáticamente al confirmarse el destino, no espera pregunta del usuario.

Sobre el costo estimado: sale de los rangos de precio del corpus mas una tabla de costos base por categoría. **No es un número inventado por el LLM.** El método de estimación se documenta, porque en la defensa lo van a preguntar.

## Orquestador

Agente de LangChain con memoria de la sesión, que recibe el estado del viaje y decide entre tres caminos: pedido de plan nuevo, respuesta a una pregunta de slot filling, o consulta puntual de recomendación.

Si el flujo se vuelve difícil de controlar con un agente de tools plano, migrar a **LangGraph** con nodos explícitos:

```
extraer_slots -> ¿completo? -> armar_plan
                            -> preguntar_faltante
```

Documentar la migración como decisión. LangGraph es parte del ecosistema LangChain, así que no compromete el requisito de la cátedra.
