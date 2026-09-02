BEGIN;

ALTER TABLE public.purchase_intents
    ALTER COLUMN telegram_identity_mapping_id DROP NOT NULL;

ALTER TABLE public.purchase_intents
    ADD COLUMN IF NOT EXISTS configured_base_price_minor BIGINT,
    ADD COLUMN IF NOT EXISTS actual_charged_price_minor BIGINT,
    ADD COLUMN IF NOT EXISTS identity_bootstrap_mode TEXT NOT NULL DEFAULT 'NONE';

UPDATE public.purchase_intents
SET configured_base_price_minor = expected_price_minor
WHERE configured_base_price_minor IS NULL;

ALTER TABLE public.purchase_intents
    ALTER COLUMN configured_base_price_minor SET NOT NULL,
    ADD CONSTRAINT purchase_intents_bootstrap_mode_check
        CHECK (identity_bootstrap_mode IN ('NONE','PRIVATE_CHAT_FINGERPRINT')),
    ADD CONSTRAINT purchase_intents_mapping_bootstrap_consistency
        CHECK (
            telegram_identity_mapping_id IS NOT NULL
            OR identity_bootstrap_mode = 'PRIVATE_CHAT_FINGERPRINT'
        );

CREATE UNIQUE INDEX purchase_intents_one_unresolved_telegram_customer_idx
    ON public.purchase_intents (creator_profile_id, fanvue_account_id, telegram_user_id)
    WHERE status IN ('CREATED','PRESENTED','CLICKED');

CREATE TABLE public.telegram_sales_prospects (
    telegram_sales_prospect_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    relationship_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    preference_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    inbound_message_count BIGINT NOT NULL DEFAULT 0 CHECK (inbound_message_count >= 0),
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    graduated_mapping_id BIGINT NULL REFERENCES public.telegram_identity_map(id) ON DELETE RESTRICT,
    graduated_at TIMESTAMPTZ NULL,
    UNIQUE (creator_profile_id, fanvue_account_id, telegram_user_id)
);

CREATE TABLE public.telegram_provisional_sales_sessions (
    provisional_session_id UUID PRIMARY KEY,
    telegram_sales_prospect_id UUID NOT NULL REFERENCES public.telegram_sales_prospects(telegram_sales_prospect_id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    photoshoot_reference TEXT NOT NULL CHECK (BTRIM(photoshoot_reference) <> ''),
    session_strategy TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','GRADUATED','EXPIRED','ABANDONED')),
    progression_stage TEXT NOT NULL DEFAULT 'DISCOVERY',
    current_position INTEGER NOT NULL DEFAULT 1 CHECK (current_position > 0),
    configured_base_price_minor BIGINT NOT NULL CHECK (configured_base_price_minor >= 300),
    actual_fingerprint_price_minor BIGINT NULL CHECK (actual_fingerprint_price_minor IS NULL OR actual_fingerprint_price_minor >= 300),
    first_purchase_intent_id UUID NULL UNIQUE REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    first_purchase_recorded_at TIMESTAMPTZ NULL,
    commercial_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    mapped_sales_session_id UUID NULL REFERENCES public.sales_sessions(sales_session_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    graduated_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX telegram_provisional_sales_sessions_one_active_idx
    ON public.telegram_provisional_sales_sessions (creator_profile_id, fanvue_account_id, telegram_user_id)
    WHERE state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT');

CREATE TABLE public.telegram_unlock_grants (
    unlock_grant_id UUID PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE CHECK (LENGTH(token_hash) = 64),
    purchase_intent_id UUID NOT NULL UNIQUE
        REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    commercial_offering_id UUID NOT NULL
        REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    commercial_publication_id UUID NOT NULL
        REFERENCES public.commercial_publications(publication_id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL CHECK (currency = UPPER(currency) AND currency ~ '^[A-Z]{3}$'),
    state TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (state IN ('ACTIVE','REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ NULL,
    last_used_at TIMESTAMPTZ NULL,
    use_count BIGINT NOT NULL DEFAULT 0 CHECK (use_count >= 0),
    audit_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE public.fanvue_fingerprint_reservations (
    fingerprint_reservation_id UUID PRIMARY KEY,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    currency TEXT NOT NULL CHECK (currency = UPPER(currency) AND currency ~ '^[A-Z]{3}$'),
    exact_price_minor BIGINT NOT NULL CHECK (exact_price_minor >= 300),
    configured_base_price_minor BIGINT NOT NULL CHECK (configured_base_price_minor >= 300),
    purchase_intent_id UUID NOT NULL
        REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    state TEXT NOT NULL DEFAULT 'RESERVED' CHECK (
        state IN ('RESERVED','ACTIVE','PURCHASED','EXPIRED','ABANDONED','RETIRED','FAILED','UNCERTAIN')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ NULL,
    purchased_at TIMESTAMPTZ NULL,
    expired_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    provider_transaction_reference TEXT NULL,
    recovery_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (fanvue_account_id, currency, exact_price_minor)
);

CREATE INDEX fanvue_fingerprint_reservations_intent_idx
    ON public.fanvue_fingerprint_reservations (purchase_intent_id, created_at DESC);

CREATE TABLE public.fanvue_runtime_media_links (
    runtime_media_link_id UUID PRIMARY KEY,
    purchase_intent_id UUID NOT NULL
        REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    fingerprint_reservation_id UUID NOT NULL UNIQUE
        REFERENCES public.fanvue_fingerprint_reservations(fingerprint_reservation_id) ON DELETE RESTRICT,
    provider_media_link_uuid TEXT NULL,
    provider_url TEXT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING_CREATE' CHECK (
        state IN ('PENDING_CREATE','CREATING','ACTIVE','PURCHASED','EXPIRED','DELETE_REQUESTED','DELETED','DELETE_FAILED','ORPHANED','UNCERTAIN','CREATE_FAILED')
    ),
    creation_operation_key UUID NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ NULL,
    last_attempt_at TIMESTAMPTZ NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error TEXT NULL,
    reconciliation_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (expires_at > created_at),
    CHECK (state <> 'ACTIVE' OR (provider_media_link_uuid IS NOT NULL AND provider_url IS NOT NULL))
);

CREATE UNIQUE INDEX fanvue_runtime_media_links_one_live_intent_idx
    ON public.fanvue_runtime_media_links (purchase_intent_id)
    WHERE state IN ('PENDING_CREATE','CREATING','ACTIVE','UNCERTAIN');

CREATE TABLE public.fanvue_runtime_media_link_operations (
    operation_id UUID PRIMARY KEY,
    runtime_media_link_id UUID NOT NULL
        REFERENCES public.fanvue_runtime_media_links(runtime_media_link_id) ON DELETE RESTRICT,
    operation_type TEXT NOT NULL CHECK (operation_type IN ('CREATE','DELETE')),
    idempotency_key UUID NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING','CLAIMED','SUCCEEDED','FAILED','UNCERTAIN')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    provider_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX fanvue_runtime_media_link_operations_due_idx
    ON public.fanvue_runtime_media_link_operations (next_attempt_at, created_at)
    WHERE state IN ('PENDING','FAILED');

COMMIT;
