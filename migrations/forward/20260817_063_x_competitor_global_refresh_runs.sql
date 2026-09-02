BEGIN;

CREATE TABLE x_intelligence.global_refresh_runs (
    id UUID PRIMARY KEY,
    refresh_type TEXT NOT NULL CHECK (refresh_type IN ('PROFILES','ACTIVITY')),
    status TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED')),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    considered INTEGER NOT NULL DEFAULT 0 CHECK (considered >= 0),
    succeeded INTEGER NOT NULL DEFAULT 0 CHECK (succeeded >= 0),
    failed INTEGER NOT NULL DEFAULT 0 CHECK (failed >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_x_global_refresh_completion CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX idx_x_global_refresh_runs_latest
    ON x_intelligence.global_refresh_runs (refresh_type, created_at DESC, id DESC);

COMMIT;
