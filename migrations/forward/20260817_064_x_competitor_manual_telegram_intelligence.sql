BEGIN;

ALTER TABLE x_intelligence.competitors
    ADD COLUMN IF NOT EXISTS telegram_audience_type TEXT,
    ADD COLUMN IF NOT EXISTS telegram_comments_allowed BOOLEAN,
    ADD COLUMN IF NOT EXISTS telegram_joined BOOLEAN;

ALTER TABLE x_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_telegram_audience_type,
    ADD CONSTRAINT ck_x_intelligence_competitors_telegram_audience_type
        CHECK (telegram_audience_type IS NULL OR telegram_audience_type IN ('SUBSCRIBERS', 'MEMBERS'));

COMMIT;
