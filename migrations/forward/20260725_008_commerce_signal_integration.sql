CREATE TABLE IF NOT EXISTS public.commerce_signal_reconciliations (
    reconciliation_id UUID PRIMARY KEY,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    provider_event_id TEXT NOT NULL,
    source_event_type TEXT NOT NULL CHECK (
        source_event_type IN ('purchase_new','creator_payment_succeeded')
    ),
    observed_transaction_id TEXT NOT NULL,
    canonical_transaction_order_id TEXT NULL,
    external_fanvue_user_uuid UUID NULL,
    purchase_type TEXT NULL,
    expected_amount_minor BIGINT NULL CHECK (
        expected_amount_minor IS NULL OR expected_amount_minor >= 0
    ),
    state TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        state IN ('PENDING','VERIFIED','FAILED')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    earnings_record JSONB NULL,
    verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fanvue_account_id, provider_event_id)
);

CREATE INDEX IF NOT EXISTS idx_commerce_signal_reconciliation_due
    ON public.commerce_signal_reconciliations (next_attempt_at, created_at)
    WHERE state='PENDING';

CREATE INDEX IF NOT EXISTS idx_commerce_signal_reconciliation_transaction
    ON public.commerce_signal_reconciliations (
        fanvue_account_id, canonical_transaction_order_id
    )
    WHERE canonical_transaction_order_id IS NOT NULL;
