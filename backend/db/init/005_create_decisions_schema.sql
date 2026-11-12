-- Capa 1 -- Decision Ledger: reemplaza la tabla unica `decision_record` por
-- 3 tablas conectadas por una maquina de estados (ver README).
DROP TABLE IF EXISTS decision_record;

-- Tabla 1: la decision (escrita en el momento de decidir)
CREATE TABLE decisions (
    decision_id           TEXT         PRIMARY KEY,
    -- Formato: dec_{YYYYMMDD}_{truck_id}_{seq}

    status                TEXT         NOT NULL DEFAULT 'PENDING_RESULT',
    -- 'PENDING_RESULT' | 'RESULT_RECEIVED' | 'PROCESSED_FOR_LEARNING' | 'ABANDONED'

    timestamp_decision    TIMESTAMPTZ  NOT NULL,
    timestamp_resultado   TIMESTAMPTZ,
    timestamp_procesado   TIMESTAMPTZ,

    vector_estado         JSONB        NOT NULL,

    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

ALTER TABLE decisions
    ADD CONSTRAINT decisions_status_check
    CHECK (status IN ('PENDING_RESULT', 'RESULT_RECEIVED', 'PROCESSED_FOR_LEARNING', 'ABANDONED'));

-- Tabla 2: los candidatos evaluados (varios por decision)
CREATE TABLE decision_candidates (
    decision_id     TEXT     NOT NULL REFERENCES decisions(decision_id),

    route_id        TEXT     NOT NULL,
    rank_posicion   INT      NOT NULL,
    fue_elegido     BOOLEAN  NOT NULL DEFAULT FALSE,

    puntaje         FLOAT,
    profit_estimado FLOAT,
    lanes           JSONB,
    scores_detalle  JSONB
);

CREATE UNIQUE INDEX idx_decision_candidates_decision_route
    ON decision_candidates (decision_id, route_id);

-- Tabla 3: el resultado real (escrita dias despues por el Reconciler)
CREATE TABLE decision_results (
    decision_id         TEXT        PRIMARY KEY REFERENCES decisions(decision_id),

    timestamp_resultado TIMESTAMPTZ NOT NULL,
    fuente              TEXT        NOT NULL DEFAULT 'TMS',

    total_millas        FLOAT,
    revenue_total        FLOAT,
    rpm_efectivo         FLOAT,
    pct_deadhead         FLOAT,
    profit_apl_real      FLOAT,
    duracion_ciclo_dias  INT,
    zona_llegada_final   TEXT,

    profit_delta         FLOAT,
    rpm_delta             FLOAT,

    lanes_ejecucion_real  JSONB  NOT NULL
);

-- Para el Reconciler: busca PENDING_RESULT con antiguedad
CREATE INDEX idx_decisions_reconciler
    ON decisions (status, timestamp_decision)
    WHERE status = 'PENDING_RESULT';

-- Para Attribution (Capa 3, futura): busca RESULT_RECEIVED listas para procesar
CREATE INDEX idx_decisions_attribution
    ON decisions (status, timestamp_decision)
    WHERE status = 'RESULT_RECEIVED';

CREATE INDEX idx_decisions_truck ON decisions ((vector_estado -> 'recurso' ->> 'truck_id'));
