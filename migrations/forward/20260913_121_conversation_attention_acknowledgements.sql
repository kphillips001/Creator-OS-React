BEGIN;

CREATE TABLE public.conversation_attention_acknowledgements (
    acknowledgement_id UUID PRIMARY KEY,
    occurrence_id TEXT NOT NULL UNIQUE,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    telegram_account_scope TEXT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    triggering_inbound_message_id BIGINT NOT NULL,
    causal_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id),
    attention_reason TEXT NOT NULL,
    predicate_version TEXT NOT NULL,
    acknowledged_by TEXT NOT NULL,
    acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ NULL,
    revoked_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_conversation_attention_ack_scope
    ON public.conversation_attention_acknowledgements(
        creator_profile_id, fanvue_account_id, telegram_user_id,
        triggering_inbound_message_id
    );

COMMENT ON TABLE public.conversation_attention_acknowledgements IS
    'Durable operator acknowledgement of one server-derived Chat attention occurrence; never outbound evidence.';

COMMIT;
