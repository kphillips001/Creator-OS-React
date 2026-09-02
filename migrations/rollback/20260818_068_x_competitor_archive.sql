BEGIN;

DROP INDEX IF EXISTS x_intelligence.idx_x_intelligence_competitors_active;
ALTER TABLE x_intelligence.competitors DROP COLUMN IF EXISTS archived_at;

COMMIT;
