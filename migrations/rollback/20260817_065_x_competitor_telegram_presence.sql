BEGIN;
ALTER TABLE x_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_telegram_presence,
    DROP COLUMN IF EXISTS telegram_presence;
COMMIT;
