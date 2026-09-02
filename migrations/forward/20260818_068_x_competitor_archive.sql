BEGIN;

ALTER TABLE x_intelligence.competitors
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_x_intelligence_competitors_active
    ON x_intelligence.competitors (created_at, id)
    WHERE archived_at IS NULL;

COMMIT;
