CREATE TABLE IF NOT EXISTS public.commerce_recommendation_outcomes (
    outcome_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    telegram_user_id BIGINT NULL,
    commercial_offering_id UUID NOT NULL
        REFERENCES public.commercial_offerings(offering_id),
    purchase_intent_id UUID NULL REFERENCES public.purchase_intents(purchase_intent_id),
    outcome_type TEXT NOT NULL CHECK (outcome_type IN (
        'PRESENTED','OPENED','PURCHASED','IGNORED','EXPIRED',
        'DECLINED','ABANDONED','REFUNDED'
    )),
    observed_at TIMESTAMPTZ NOT NULL,
    source_event_key TEXT NOT NULL UNIQUE,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommendation_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commerce_recommendation_outcomes_customer
    ON public.commerce_recommendation_outcomes (
        creator_profile_id,fanvue_account_id,external_fanvue_user_uuid,observed_at DESC
    );

CREATE TABLE IF NOT EXISTS public.customer_commerce_learning_profiles (
    learning_profile_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    telegram_user_id BIGINT NULL,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    preferred_offering_type TEXT NULL,
    favorite_media_type TEXT NULL,
    average_price_minor INTEGER NULL,
    preferred_price_min_minor INTEGER NULL,
    preferred_price_max_minor INTEGER NULL,
    repeat_purchase_frequency DOUBLE PRECISION NOT NULL DEFAULT 0,
    average_purchase_interval_days DOUBLE PRECISION NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    last_observed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (creator_profile_id,fanvue_account_id,external_fanvue_user_uuid)
);
