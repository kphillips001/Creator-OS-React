BEGIN;

ALTER TABLE x_intelligence.competitors
    ADD COLUMN IF NOT EXISTS platform TEXT;

UPDATE x_intelligence.competitors
SET platform = 'FANVUE';

ALTER TABLE x_intelligence.competitors
    ALTER COLUMN platform SET DEFAULT 'FANVUE',
    ALTER COLUMN platform SET NOT NULL,
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_platform,
    ADD CONSTRAINT ck_x_intelligence_competitors_platform
        CHECK (platform IN ('FANVUE', 'ONLYFANS', 'OTHER'));

COMMIT;
