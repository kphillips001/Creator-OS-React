BEGIN;

ALTER TABLE x_intelligence.competitor_sync_runs
    ADD COLUMN canonical_refresh BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX uq_x_competitor_sync_runs_active_refresh
    ON x_intelligence.competitor_sync_runs (competitor_id)
    WHERE status = 'RUNNING' AND canonical_refresh;

CREATE INDEX idx_x_competitor_sync_runs_refresh_schedule
    ON x_intelligence.competitor_sync_runs
    (canonical_refresh, status, completed_at DESC, competitor_id);

COMMIT;
