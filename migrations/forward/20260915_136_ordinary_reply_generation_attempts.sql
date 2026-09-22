BEGIN;

CREATE TABLE public.ordinary_reply_generation_attempts (
    attempt_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    creator_profile_id BIGINT NULL,
    fanvue_account_id BIGINT NULL,
    telegram_account_scope TEXT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    provider TEXT NULL,
    candidate_text TEXT NOT NULL CHECK (length(candidate_text) <= 2000),
    quality_disposition TEXT NOT NULL CHECK (quality_disposition IN ('ALLOWED_BEFORE_DELIVERY','BLOCKED_BEFORE_DELIVERY')),
    quality_reasons JSONB NOT NULL DEFAULT '[]'::JSONB,
    turn_obligations JSONB NOT NULL DEFAULT '[]'::JSONB,
    satisfied_obligations JSONB NOT NULL DEFAULT '[]'::JSONB,
    unsatisfied_obligations JSONB NOT NULL DEFAULT '[]'::JSONB,
    repair_outcome TEXT NULL,
    sent_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    outbound_telegram_message_id BIGINT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_confirmed_at TIMESTAMPTZ NULL,
    UNIQUE(operation_id, attempt_number)
);

CREATE INDEX ordinary_reply_generation_attempt_scope_idx
    ON public.ordinary_reply_generation_attempts(
        creator_profile_id, fanvue_account_id, telegram_user_id, attempted_at DESC
    );

COMMIT;
