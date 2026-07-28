CREATE TABLE IF NOT EXISTS public.purchase_intents (
    purchase_intent_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_identity_mapping_id BIGINT NOT NULL
        REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    external_fanvue_user_uuid UUID NULL,
    commercial_offering_id UUID NOT NULL
        REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    commercial_publication_id UUID NOT NULL
        REFERENCES public.commercial_publications(publication_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (provider IN ('FANVUE')),
    provider_resource_id TEXT NOT NULL CHECK (BTRIM(provider_resource_id) <> ''),
    delivery_url TEXT NOT NULL CHECK (BTRIM(delivery_url) <> ''),
    telegram_message_id BIGINT NULL,
    conversation_id TEXT NULL,
    correlation_id UUID NOT NULL,
    expected_price_minor BIGINT NOT NULL CHECK (expected_price_minor >= 0),
    expected_currency TEXT NOT NULL CHECK (
        expected_currency = UPPER(expected_currency)
        AND expected_currency ~ '^[A-Z]{3}$'
    ),
    status TEXT NOT NULL DEFAULT 'CREATED' CHECK (
        status IN (
            'CREATED','PRESENTED','CLICKED','PURCHASED','EXPIRED',
            'ABANDONED','UNKNOWN','SUPERSEDED'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    presented_at TIMESTAMPTZ NULL,
    clicked_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    abandoned_at TIMESTAMPTZ NULL,
    purchased_at TIMESTAMPTZ NULL,
    provider_transaction_order_id TEXT NULL,
    provider_payment_id TEXT NULL,
    provider_event_id TEXT NULL,
    attribution_result TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        attribution_result IN ('PENDING','ATTRIBUTED','UNKNOWN')
    ),
    attribution_reason TEXT NULL,
    created_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > created_at),
    CHECK (status <> 'PRESENTED' OR presented_at IS NOT NULL),
    CHECK (status <> 'CLICKED' OR clicked_at IS NOT NULL),
    CHECK (status <> 'PURCHASED' OR purchased_at IS NOT NULL),
    CHECK (status <> 'ABANDONED' OR abandoned_at IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_intents_active_buyer
    ON public.purchase_intents (
        creator_profile_id, fanvue_account_id, telegram_user_id
    )
    WHERE status IN ('CREATED','PRESENTED','CLICKED');

CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_intents_provider_transaction
    ON public.purchase_intents (
        fanvue_account_id, provider, provider_transaction_order_id
    )
    WHERE provider_transaction_order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_intents_provider_payment
    ON public.purchase_intents (
        fanvue_account_id, provider, provider_payment_id
    )
    WHERE provider_payment_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_intents_provider_event
    ON public.purchase_intents (
        fanvue_account_id, provider, provider_event_id
    )
    WHERE provider_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_purchase_intents_creator_created
    ON public.purchase_intents (creator_profile_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_purchase_intents_due
    ON public.purchase_intents (expires_at)
    WHERE status IN ('CREATED','PRESENTED','CLICKED');

CREATE INDEX IF NOT EXISTS idx_purchase_intents_offering
    ON public.purchase_intents (commercial_offering_id, created_at DESC);
