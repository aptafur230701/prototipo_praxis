-- Manifiesto: tablero de control activo del sistema (Capa 4 -- Gobernanza)
CREATE TABLE production_manifest (
    id               SERIAL      PRIMARY KEY,
    ambiente         TEXT        NOT NULL DEFAULT 'produccion',

    champion_id      TEXT        NOT NULL REFERENCES artifacts(artifact_id),
    champion_desde   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    champion_por     TEXT,

    challenger_id    TEXT        REFERENCES artifacts(artifact_id),
    -- NULL si no hay challenger en evaluacion
    challenger_desde TIMESTAMPTZ,
    -- Fecha en que se registro el challenger actual

    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_por      TEXT,
    notas            TEXT
);

CREATE UNIQUE INDEX idx_production_manifest_ambiente ON production_manifest (ambiente);

INSERT INTO production_manifest (ambiente, champion_id, champion_por)
VALUES ('produccion', 'scoring_policy_v1', 'setup_inicial');
