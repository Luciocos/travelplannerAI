-- Esquema base del asistente de viajes.
-- documento_rag cubre los tres corpus de RAG (atractivos, comercios, faq).
-- itinerario/itinerario_item y gasto/participante son tablas propias, viven
-- en la misma base que los vectores (ver arquitectura.md, decision D-01).

CREATE EXTENSION IF NOT EXISTS vector;

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
