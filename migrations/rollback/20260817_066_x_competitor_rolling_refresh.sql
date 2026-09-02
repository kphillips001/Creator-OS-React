BEGIN;

DROP INDEX IF EXISTS x_intelligence.idx_x_competitor_sync_runs_refresh_schedule;
DROP INDEX IF EXISTS x_intelligence.uq_x_competitor_sync_runs_active_refresh;
ALTER TABLE x_intelligence.competitor_sync_runs DROP COLUMN IF EXISTS canonical_refresh;

COMMIT;
