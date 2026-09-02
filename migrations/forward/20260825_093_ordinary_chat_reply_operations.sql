BEGIN;

CREATE TABLE public.ordinary_chat_reply_operations (
    operation_id UUID PRIMARY KEY,
    telegram_account_scope TEXT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    inbound_telegram_message_id BIGINT NOT NULL,
    inbound_sender_telegram_user_id BIGINT NOT NULL,
    conversation_thread_id BIGINT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    correlation_id TEXT NOT NULL UNIQUE,
    response_payload JSONB NULL,
    response_text TEXT NULL,
    response_content_sha256 TEXT NULL CHECK (
        response_content_sha256 IS NULL OR length(response_content_sha256)=64
    ),
    delivery_payload JSONB NULL,
    state TEXT NOT NULL DEFAULT 'PENDING_GENERATION' CHECK (state IN (
        'PENDING_GENERATION','GENERATING','GENERATED','SENDING','SENT_CONFIRMED',
        'RETRYABLE','SEND_UNCERTAIN','TERMINAL_FAILED','SUPPRESSED'
    )),
    outbound_telegram_message_id BIGINT NULL,
    generation_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (generation_attempt_count>=0),
    send_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (send_attempt_count>=0),
    max_generation_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_generation_attempts>0),
    max_send_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_send_attempts>0),
    claim_owner TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    next_retry_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    generated_at TIMESTAMPTZ NULL,
    sending_at TIMESTAMPTZ NULL,
    sent_confirmed_at TIMESTAMPTZ NULL,
    uncertain_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (telegram_account_scope,telegram_chat_id,inbound_telegram_message_id)
);

CREATE INDEX ordinary_chat_reply_operations_recovery_idx
    ON public.ordinary_chat_reply_operations(state,next_retry_at,lease_expires_at)
    WHERE state IN ('PENDING_GENERATION','GENERATING','GENERATED','SENDING','RETRYABLE');

COMMIT;
