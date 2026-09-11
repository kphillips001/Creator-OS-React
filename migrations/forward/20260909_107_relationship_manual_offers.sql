BEGIN;

CREATE TABLE public.telegram_manual_offer_operations (
    operation_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    telegram_identity_mapping_id BIGINT NOT NULL REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NOT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    commercial_offering_id UUID NOT NULL REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    commercial_publication_id UUID NOT NULL REFERENCES public.commercial_publications(publication_id) ON DELETE RESTRICT,
    business_connection_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    message_text TEXT NOT NULL CHECK (BTRIM(message_text) <> ''),
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
    relationship_control_version BIGINT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'HUMAN_OPERATOR_PRESENTED'
        CHECK (origin='HUMAN_OPERATOR_PRESENTED'),
    state TEXT NOT NULL DEFAULT 'PREPARED' CHECK (state IN (
        'PREPARED','SENDING','CONFIRMED','FAILED','AMBIGUOUS'
    )),
    purchase_intent_id UUID NULL REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    sales_delivery_operation_id UUID NULL REFERENCES public.telegram_sales_delivery_operations(operation_id) ON DELETE RESTRICT,
    outbound_telegram_message_id BIGINT NULL,
    last_error TEXT NULL,
    sending_at TIMESTAMPTZ NULL,
    confirmed_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    ambiguous_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
);

CREATE INDEX telegram_manual_offer_recovery_idx
    ON public.telegram_manual_offer_operations(state,updated_at)
    WHERE state IN ('PREPARED','SENDING');

COMMIT;
