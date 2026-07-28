BEGIN;

CREATE TABLE IF NOT EXISTS public.customer_commerce_profiles (
    customer_commerce_profile_id UUID PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    telegram_identity_mapping_id BIGINT NULL
        REFERENCES public.telegram_identity_map(id) ON DELETE SET NULL,
    telegram_user_id BIGINT NULL,
    display_name TEXT NULL,
    handle TEXT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    first_purchase_at TIMESTAMPTZ NULL,
    last_purchase_at TIMESTAMPTZ NULL,
    lifetime_gross_minor BIGINT NOT NULL DEFAULT 0,
    lifetime_net_minor BIGINT NOT NULL DEFAULT 0,
    purchase_count INTEGER NOT NULL DEFAULT 0,
    average_order_value_minor BIGINT NOT NULL DEFAULT 0,
    largest_purchase_minor BIGINT NOT NULL DEFAULT 0,
    last_transaction_order_id TEXT NULL,
    last_payment_status TEXT NULL,
    last_purchase_source TEXT NULL,
    last_synced_at TIMESTAMPTZ NULL,
    profile_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT customer_commerce_profile_buyer_unique
        UNIQUE (creator_profile_id, external_fanvue_user_uuid),
    CONSTRAINT customer_commerce_profile_state_check CHECK (
        profile_state IN (
            'UNKNOWN', 'PROSPECT', 'LEAD', 'FIRST_PURCHASE',
            'REPEAT_BUYER', 'VIP', 'HIGH_VALUE', 'INACTIVE'
        )
    ),
    CONSTRAINT customer_commerce_profile_totals_check CHECK (
        lifetime_gross_minor >= 0
        AND lifetime_net_minor >= 0
        AND purchase_count >= 0
        AND average_order_value_minor >= 0
        AND largest_purchase_minor >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_customer_commerce_profiles_account_buyer
    ON public.customer_commerce_profiles (
        fanvue_account_id, external_fanvue_user_uuid
    );
CREATE INDEX IF NOT EXISTS idx_customer_commerce_profiles_creator_activity
    ON public.customer_commerce_profiles (
        creator_profile_id, last_purchase_at DESC NULLS LAST, last_seen_at DESC
    );

CREATE TABLE IF NOT EXISTS public.customer_commerce_transactions (
    customer_commerce_transaction_id UUID PRIMARY KEY,
    customer_commerce_profile_id UUID NOT NULL
        REFERENCES public.customer_commerce_profiles(
            customer_commerce_profile_id
        ) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    transaction_order_id TEXT NOT NULL,
    gross_minor BIGINT NOT NULL,
    net_minor BIGINT NOT NULL,
    payment_status TEXT NOT NULL,
    purchase_source TEXT NOT NULL,
    payment_timestamp TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT customer_commerce_transaction_provider_unique
        UNIQUE (fanvue_account_id, transaction_order_id),
    CONSTRAINT customer_commerce_transaction_amounts_check CHECK (
        gross_minor >= 0 AND net_minor >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_customer_commerce_transactions_profile
    ON public.customer_commerce_transactions (
        customer_commerce_profile_id, payment_timestamp DESC
    );

COMMIT;
