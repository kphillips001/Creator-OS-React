BEGIN;
ALTER TABLE x_intelligence.competitors
    DROP COLUMN IF EXISTS telegram_url;
COMMIT;
