-- Persistencia de chats (Fase 7C). Antes SesionAgente vivia solo en
-- memoria del proceso (RF11 alcanzaba para una sesion, no para "guardar
-- charlas y poder volver a ellas", un bug real encontrado probando la
-- app: refrescar la pagina perdia toda la conversacion).
--
-- `mensaje` es la fuente de verdad del historial (lo que ve el LLM en
-- PROMPT_INTERPRETAR_TURNO/PROMPT_CONVERSAR se reconstruye de aca, no del
-- jsonb de `conversacion`). `conversacion.sesion` guarda solo el estado
-- derivado (PreferenciasViaje, el ultimo plan armado, para que dato de
-- info_destino ya se mostro) para no duplicar el historial en dos
-- lugares que puedan desincronizarse.

CREATE TABLE IF NOT EXISTS conversacion (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    titulo        TEXT NOT NULL DEFAULT 'Nueva conversación',
    titulo_manual BOOLEAN NOT NULL DEFAULT false,  -- true si el usuario lo renombro (no se pisa solo)
    esquema_version INTEGER NOT NULL DEFAULT 1,    -- ver conversaciones.py: si el modelo de sesion cambia, un chat viejo degrada a estado vacio en vez de romper
    sesion        JSONB NOT NULL DEFAULT '{}'::jsonb,
    creada_en     TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizada_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mensaje (
    id             BIGSERIAL PRIMARY KEY,
    conversacion_id UUID NOT NULL REFERENCES conversacion (id) ON DELETE CASCADE,
    orden          INTEGER NOT NULL,
    rol            TEXT NOT NULL CHECK (rol IN ('usuario', 'asistente')),
    texto          TEXT NOT NULL,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversacion_id, orden)
);

CREATE INDEX IF NOT EXISTS idx_mensaje_conversacion ON mensaje (conversacion_id, orden);

-- Vincula un itinerario armado con la conversacion donde se armo (para
-- poder ofrecer "descargar el ultimo plan" desde la UI). Nullable y
-- ON DELETE SET NULL: borrar una conversacion no tiene por que borrar un
-- itinerario ya persistido.
ALTER TABLE itinerario ADD COLUMN IF NOT EXISTS conversacion_id UUID REFERENCES conversacion (id) ON DELETE SET NULL;
