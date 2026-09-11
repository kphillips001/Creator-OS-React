BEGIN;

ALTER TABLE public.telegram_relationship_controls
    DROP COLUMN IF EXISTS session_selling_enabled,
    DROP COLUMN IF EXISTS content_selling_enabled;

COMMIT;
