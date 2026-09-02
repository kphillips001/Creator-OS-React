BEGIN;
ALTER TABLE public.ordinary_chat_reply_operations
    ADD COLUMN IF NOT EXISTS inbound_message_text TEXT NULL,
    ADD COLUMN IF NOT EXISTS inbound_received_at TIMESTAMPTZ NULL;
CREATE TABLE IF NOT EXISTS public.controlled_test_reset_audit (
    reset_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scope TEXT NOT NULL CHECK (scope='CONTROLLED_TELEGRAM_TEST'),
    identity_fingerprint TEXT NOT NULL,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    removed_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_preconditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    commerce_preserved BOOLEAN NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('SUCCEEDED','BLOCKED','FAILED')),
    failure_reason TEXT NULL
);
COMMIT;
