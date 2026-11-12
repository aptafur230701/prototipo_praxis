-- Praxis / Knowledge State - Capa 2: Artefactos
-- Inventario de todos los artefactos del sistema (modelos y politicas de scoring).

CREATE TABLE artifacts (
    artifact_id     TEXT         PRIMARY KEY,
    -- Formato: {tipo}_v{version} -- Ej: scoring_policy_v1

    tipo            TEXT         NOT NULL
                                  CHECK (tipo IN ('scoring_policy', 'rate_model')),

    status          TEXT         NOT NULL DEFAULT 'CANDIDATE'
                                  CHECK (status IN ('TRAINING', 'CANDIDATE', 'CHALLENGER', 'CHAMPION', 'RETIRED')),

    parametros      JSONB,
    -- Para artefactos cuyos pesos caben en memoria.
    -- Ej: {"w_pf": 150.0, "w_ef": 45.0, "w_vd": 100.0}

    archivo_path    TEXT,
    -- Para modelos almacenados en S3.
    -- Ej: s3://bucket/models/scoring_policy_v1.joblib

    training_desde  DATE,
    training_hasta  DATE,
    n_decisiones    INT,

    metricas        JSONB,
    -- Ej: {"profit_per_day_prom": 850, "CoC_prom": 83, "pct_rutas_caidas": 19}

    descripcion     TEXT,
    entrenado_por   TEXT,
    notas           TEXT,

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    promoted_at     TIMESTAMPTZ,
    retired_at      TIMESTAMPTZ,

    CONSTRAINT artifacts_source_check
        CHECK (parametros IS NOT NULL OR archivo_path IS NOT NULL)
);

CREATE INDEX idx_artifacts_status ON artifacts (status);
CREATE INDEX idx_artifacts_tipo ON artifacts (tipo);

-- Historial de que artefacto fue champion y por cuanto tiempo.
CREATE TABLE artifact_champion_history (
    id                BIGSERIAL   PRIMARY KEY,
    artifact_id       TEXT        NOT NULL REFERENCES artifacts (artifact_id),
    fue_campeon_desde TIMESTAMPTZ NOT NULL,
    fue_campeon_hasta TIMESTAMPTZ,  -- NULL = sigue siendo campeon actualmente
    razon_retiro      TEXT
);

CREATE INDEX idx_champion_history_artifact ON artifact_champion_history (artifact_id);

-- Garantiza que un artefacto no tenga dos periodos de "campeon actual" abiertos a la vez.
CREATE UNIQUE INDEX idx_champion_history_open_period
    ON artifact_champion_history (artifact_id)
    WHERE fue_campeon_hasta IS NULL;
