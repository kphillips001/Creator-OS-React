CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_intents_telegram_correlation
    ON public.purchase_intents (correlation_id);

CREATE TABLE IF NOT EXISTS public.telegram_sales_delivery_operations (
    operation_id UUID PRIMARY KEY,
    correlation_id TEXT NOT NULL UNIQUE CHECK (BTRIM(correlation_id) <> ''),
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NOT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    inbound_telegram_message_id BIGINT NOT NULL,
    outbound_telegram_message_id BIGINT NULL,
    purchase_intent_id UUID NOT NULL UNIQUE REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    commercial_offering_id UUID NOT NULL REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    commercial_publication_id UUID NOT NULL REFERENCES public.commercial_publications(publication_id) ON DELETE RESTRICT,
    response_text TEXT NOT NULL,
    delivery_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    state TEXT NOT NULL CHECK (state IN ('CREATED','SENDING','TELEGRAM_ACCEPTED','CONFIRMED','FAILED','AMBIGUOUS')),
    failure_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sending_at TIMESTAMPTZ NULL,
    telegram_accepted_at TIMESTAMPTZ NULL,
    confirmed_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (telegram_chat_id, inbound_telegram_message_id)
);

CREATE INDEX IF NOT EXISTS idx_telegram_sales_delivery_incomplete
    ON public.telegram_sales_delivery_operations (state, updated_at)
    WHERE state IN ('CREATED','SENDING','TELEGRAM_ACCEPTED','AMBIGUOUS');
