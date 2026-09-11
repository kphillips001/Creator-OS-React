BEGIN;

CREATE TABLE public.telegram_relationship_controls (
    relationship_control_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    telegram_identity_mapping_id BIGINT NULL REFERENCES public.telegram_identity_map(id) ON DELETE SET NULL,
    local_fanvue_user_id BIGINT NULL REFERENCES public.fanvue_users(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (mode IN ('AVA_AUTO','HUMAN_OPERATOR')),
    control_version BIGINT NOT NULL DEFAULT 0 CHECK (control_version >= 0),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by TEXT NOT NULL,
    reason TEXT NULL,
    last_manual_activity_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id,fanvue_account_id,telegram_user_id)
);

CREATE TABLE public.telegram_operator_message_operations (
    operation_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    telegram_identity_mapping_id BIGINT NULL REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    message_text TEXT NOT NULL CHECK (BTRIM(message_text) <> ''),
    message_sha256 TEXT NOT NULL CHECK (length(message_sha256)=64),
    relationship_control_version BIGINT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'HUMAN_OPERATOR' CHECK (origin='HUMAN_OPERATOR'),
    state TEXT NOT NULL DEFAULT 'PREPARED' CHECK (state IN (
        'PREPARED','SENDING','CONFIRMED','FAILED','AMBIGUOUS'
    )),
    outbound_telegram_message_id BIGINT NULL,
    send_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (send_attempt_count >= 0),
    changed_by TEXT NOT NULL,
    last_error TEXT NULL,
    sending_at TIMESTAMPTZ NULL,
    confirmed_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    ambiguous_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
);

CREATE INDEX telegram_operator_message_recovery_idx
    ON public.telegram_operator_message_operations(state,updated_at)
    WHERE state IN ('PREPARED','SENDING');

COMMIT;
