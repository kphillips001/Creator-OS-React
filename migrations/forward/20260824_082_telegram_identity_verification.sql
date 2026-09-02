ALTER TABLE public.telegram_identity_map
    ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    ADD COLUMN IF NOT EXISTS verification_method TEXT NULL,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS verified_by TEXT NULL,
    ADD COLUMN IF NOT EXISTS verification_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_observed_username TEXT NULL,
    ADD COLUMN IF NOT EXISTS last_observed_display_name TEXT NULL;

ALTER TABLE public.telegram_identity_map
    DROP CONSTRAINT IF EXISTS telegram_identity_map_verification_status_check;
ALTER TABLE public.telegram_identity_map
    ADD CONSTRAINT telegram_identity_map_verification_status_check
    CHECK (verification_status IN ('UNVERIFIED','VERIFIED','CONFLICT'));

CREATE TABLE IF NOT EXISTS public.telegram_identity_observations (
    telegram_user_id BIGINT PRIMARY KEY CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    username TEXT NULL,
    display_name TEXT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.telegram_identity_verification_audit (
    audit_id UUID PRIMARY KEY,
    telegram_identity_mapping_id BIGINT NOT NULL
        REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('VERIFIED','METADATA_REFRESHED')),
    verification_method TEXT NOT NULL,
    operator_source TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_identity_verification_status
    ON public.telegram_identity_map (verification_status,is_active);

