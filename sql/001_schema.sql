-- Esquema base del asistente de viajes.
-- documento_rag cubre los tres corpus de RAG (atractivos, comercios, faq).
-- itinerario/itinerario_item y gasto/participante son tablas propias, viven
-- en la misma base que los vectores (ver arquitectura.md, decision D-01).

CREATE EXTENSION IF NOT EXISTS vector;
-- unaccent: el destino puede llegar del usuario con o sin tilde (ej. la
-- forma correcta en espaniol vs. como puede tipearlo alguien), y el
-- filtro por destino tiene que ser insensible a eso (ver consulta
-- canonica en recuperacion/_consulta.py).
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS documento_rag (
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

CREATE INDEX IF NOT EXISTS idx_documento_rag_filtro ON documento_rag (corpus, destino);
CREATE INDEX IF NOT EXISTS idx_documento_rag_emb ON documento_rag
    USING hnsw (embedding vector_cosine_ops);

-- Tablas de itinerario (RF5, Fase 6). Estructura minima, se ajusta en esa fase.
CREATE TABLE IF NOT EXISTS itinerario (
    id                BIGSERIAL PRIMARY KEY,
    destino           TEXT NOT NULL,
    fecha_inicio      DATE,
    fecha_fin         DATE,
    cantidad_personas INTEGER,
    presupuesto       TEXT,
    costo_estimado    NUMERIC,
    creado_en         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS itinerario_item (
    id            BIGSERIAL PRIMARY KEY,
    itinerario_id BIGINT NOT NULL REFERENCES itinerario (id) ON DELETE CASCADE,
    dia           INTEGER NOT NULL,
    orden         INTEGER NOT NULL,
    documento_id  BIGINT REFERENCES documento_rag (id),
    descripcion   TEXT NOT NULL,
    costo_estimado NUMERIC
);

-- Cache de resolucion de destinos para RapidAPI (RF6/RF7, Fase 7, D-06).
-- Booking.com15 y Fly Scraper no aceptan un nombre de ciudad como parametro
-- de busqueda directo, hay que resolverlo antes a un id propio de cada API.
-- Esa resolucion no cambia nunca para un mismo destino, asi que se cachea
-- para no quemar la cuota Free en cada corrida.
CREATE TABLE IF NOT EXISTS destino_externo (
    id               SERIAL PRIMARY KEY,
    proveedor        TEXT NOT NULL,        -- 'booking' | 'fly_scraper'
    texto_consultado TEXT NOT NULL,        -- normalizado: lower, sin tildes, trim
    id_externo       TEXT NOT NULL,
    tipo             TEXT,
    payload          JSONB NOT NULL,       -- respuesta cruda, para re-parsear sin volver a llamar
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (proveedor, texto_consultado)
);

-- Contador de llamadas por proveedor RapidAPI y mes, para el guard de cuota
-- del plan Free (ver migracion-amadeus-a-rapidapi.md, seccion 5).
CREATE TABLE IF NOT EXISTS uso_api_mensual (
    proveedor  TEXT NOT NULL,
    periodo    TEXT NOT NULL,   -- 'YYYY-MM'
    cantidad   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (proveedor, periodo)
);

-- Tablas de gastos (RF10, extension, Fase 7).
CREATE TABLE IF NOT EXISTS participante (
    id            BIGSERIAL PRIMARY KEY,
    itinerario_id BIGINT NOT NULL REFERENCES itinerario (id) ON DELETE CASCADE,
    nombre        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gasto (
    id              BIGSERIAL PRIMARY KEY,
    itinerario_id   BIGINT NOT NULL REFERENCES itinerario (id) ON DELETE CASCADE,
    participante_id BIGINT NOT NULL REFERENCES participante (id) ON DELETE CASCADE,
    concepto        TEXT NOT NULL,
    monto           NUMERIC NOT NULL,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);
