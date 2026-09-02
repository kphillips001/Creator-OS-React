BEGIN;
ALTER TABLE x_intelligence.competitors
    DROP COLUMN IF EXISTS telegram_scraped;
COMMIT;
