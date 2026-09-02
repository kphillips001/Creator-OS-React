BEGIN;

ALTER TABLE x_intelligence.competitors
    DROP CONSTRAINT IF EXISTS ck_x_intelligence_competitors_telegram_audience_type,
    DROP COLUMN IF EXISTS telegram_joined,
    DROP COLUMN IF EXISTS telegram_comments_allowed,
    DROP COLUMN IF EXISTS telegram_audience_type;

COMMIT;
