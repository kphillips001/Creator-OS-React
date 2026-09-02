BEGIN;
ALTER TABLE x_intelligence.competitors
    ADD COLUMN IF NOT EXISTS telegram_url TEXT;
COMMIT;
