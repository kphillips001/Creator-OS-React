BEGIN;

ALTER TABLE public.telegram_relationship_controls
    ALTER COLUMN content_selling_enabled SET DEFAULT TRUE,
    ALTER COLUMN session_selling_enabled SET DEFAULT TRUE;

COMMENT ON COLUMN public.telegram_relationship_controls.content_selling_enabled IS
    'Customer-specific restriction beneath the global content-selling ceiling; defaults enabled.';
COMMENT ON COLUMN public.telegram_relationship_controls.session_selling_enabled IS
    'Customer-specific restriction beneath the global session-selling ceiling; defaults enabled.';

COMMIT;
