-- Praxis / Knowledge State - Capa 1: Registro de Experiencia (Decision Ledger)
-- Captura el vector de estado (contexto completo) en el momento en que se crea una ruta.
-- Recibira columnas adicionales en tareas futuras (rutas candidatas, ruta recomendada,
-- resultado economico real).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE decision_record (
    decision_id     TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    truck_id        TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    vector_estado   JSONB       NOT NULL
    -- Mas columnas se anadiran en tareas futuras
);

CREATE INDEX idx_decision_record_truck ON decision_record (truck_id);
CREATE INDEX idx_decision_record_created_at ON decision_record (created_at);
