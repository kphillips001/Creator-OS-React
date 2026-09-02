BEGIN;
ALTER TABLE x_intelligence.competitors ADD COLUMN IF NOT EXISTS telegram_presence TEXT NOT NULL DEFAULT 'UNKNOWN';
UPDATE x_intelligence.competitors SET telegram_presence='YES'
WHERE telegram_presence='UNKNOWN' AND (telegram_audience_type IS NOT NULL OR telegram_comments_allowed IS NOT NULL OR telegram_joined IS NOT NULL);
ALTER TABLE x_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_telegram_presence,
    ADD CONSTRAINT ck_x_intelligence_competitors_telegram_presence CHECK (telegram_presence IN ('UNKNOWN','YES','NO'));
COMMIT;
