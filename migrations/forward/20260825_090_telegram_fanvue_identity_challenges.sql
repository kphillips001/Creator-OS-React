BEGIN;

CREATE TABLE public.telegram_identity_verification_challenges (
    challenge_id UUID PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    token_hash TEXT NOT NULL UNIQUE CHECK (BTRIM(token_hash) <> ''),
    state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING','VERIFIED','EXPIRED','CANCELLED','FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL,
    provider_event_id TEXT NULL,
    provider_fanvue_user_uuid UUID NULL,
    verification_method TEXT NOT NULL DEFAULT 'FANVUE_DM_CHALLENGE',
    resulting_identity_mapping_id BIGINT NULL
        REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    verification_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > created_at),
    CHECK (state <> 'VERIFIED' OR (
        consumed_at IS NOT NULL
        AND provider_fanvue_user_uuid IS NOT NULL
        AND resulting_identity_mapping_id IS NOT NULL
    ))
);

CREATE UNIQUE INDEX idx_telegram_identity_challenge_pending_user
    ON public.telegram_identity_verification_challenges (
        telegram_user_id, fanvue_account_id
    ) WHERE state = 'PENDING';

CREATE UNIQUE INDEX idx_telegram_identity_challenge_provider_event
    ON public.telegram_identity_verification_challenges (provider_event_id)
    WHERE provider_event_id IS NOT NULL;

CREATE INDEX idx_telegram_identity_challenge_expiration
    ON public.telegram_identity_verification_challenges (expires_at)
    WHERE state = 'PENDING';

COMMIT;
