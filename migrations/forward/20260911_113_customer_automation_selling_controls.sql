BEGIN;

ALTER TABLE public.telegram_relationship_controls
    ADD COLUMN content_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN session_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.telegram_relationship_controls.content_selling_enabled IS
    'Customer-specific ceiling for new ordinary-content selling; global authority still applies.';
COMMENT ON COLUMN public.telegram_relationship_controls.session_selling_enabled IS
    'Customer-specific ceiling for new session selling; global authority still applies.';

COMMIT;
