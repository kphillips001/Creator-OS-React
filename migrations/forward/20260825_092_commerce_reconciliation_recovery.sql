BEGIN;

CREATE TABLE public.commerce_backlog_recovery_batches (
    recovery_batch_id UUID PRIMARY KEY,
    batch_name TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('HISTORICAL_RECOVERY')),
    state TEXT NOT NULL DEFAULT 'FROZEN' CHECK (
        state IN ('FROZEN','DRY_RUN_CERTIFIED','RECOVERING','COMPLETED','BLOCKED')
    ),
    frozen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    frozen_row_count INTEGER NOT NULL CHECK (frozen_row_count >= 0),
    snapshot_checksum TEXT NOT NULL CHECK (length(snapshot_checksum)=64),
    dry_run_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    recovery_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE public.commerce_backlog_recovery_items (
    recovery_batch_id UUID NOT NULL REFERENCES public.commerce_backlog_recovery_batches(recovery_batch_id) ON DELETE RESTRICT,
    webhook_event_id BIGINT NOT NULL REFERENCES public.webhook_events(id) ON DELETE RESTRICT,
    internal_event_id UUID NOT NULL,
    external_event_id TEXT NULL,
    event_type TEXT NOT NULL,
    frozen_status TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
    transaction_id TEXT NULL,
    external_fanvue_user_uuid UUID NULL,
    commerce_relevance TEXT NOT NULL CHECK (commerce_relevance IN ('COMMERCE','COMMERCE_LIFECYCLE','NON_COMMERCE','CUSTOMER_MESSAGE')),
    transaction_family_key TEXT NULL,
    intended_disposition TEXT NOT NULL CHECK (intended_disposition IN ('HISTORICAL_RECOVERY','IGNORED','QUARANTINED','MANUAL_REVIEW')),
    dry_run_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_disposition TEXT NULL,
    dispositioned_at TIMESTAMPTZ NULL,
    PRIMARY KEY (recovery_batch_id,webhook_event_id)
);

CREATE INDEX commerce_backlog_recovery_items_disposition_idx
    ON public.commerce_backlog_recovery_items(recovery_batch_id,intended_disposition,webhook_event_id);

ALTER TABLE public.commerce_signal_reconciliations
    ADD COLUMN IF NOT EXISTS reconciliation_mode TEXT NOT NULL DEFAULT 'LIVE',
    ADD COLUMN IF NOT EXISTS transaction_family_key TEXT NULL,
    ADD COLUMN IF NOT EXISTS claim_owner TEXT NULL,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 8,
    ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMPTZ NULL;

ALTER TABLE public.commerce_signal_reconciliations
    ADD CONSTRAINT commerce_signal_reconciliations_mode_check
        CHECK (reconciliation_mode IN ('LIVE','HISTORICAL_RECOVERY')),
    ADD CONSTRAINT commerce_signal_reconciliations_max_attempts_check
        CHECK (max_attempts > 0);

CREATE UNIQUE INDEX commerce_signal_reconciliation_transaction_family_uidx
    ON public.commerce_signal_reconciliations(fanvue_account_id,transaction_family_key)
    WHERE transaction_family_key IS NOT NULL;

CREATE INDEX commerce_signal_reconciliation_claim_idx
    ON public.commerce_signal_reconciliations(state,next_attempt_at,lease_expires_at)
    WHERE state IN ('PENDING','FAILED');

CREATE TABLE public.commerce_signal_reconciliation_evidence (
    evidence_id UUID PRIMARY KEY,
    reconciliation_id UUID NOT NULL REFERENCES public.commerce_signal_reconciliations(reconciliation_id) ON DELETE RESTRICT,
    webhook_event_id BIGINT NULL REFERENCES public.webhook_events(id) ON DELETE RESTRICT,
    provider_event_id TEXT NOT NULL,
    source_event_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider_event_id),
    UNIQUE (reconciliation_id,source_event_type,provider_event_id)
);

CREATE TABLE public.provider_purchase_asset_ownership (
    ownership_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    provider_transaction_id TEXT NOT NULL,
    provider_resource_id TEXT NOT NULL,
    content_item_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    purchase_timestamp TIMESTAMPTZ NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fanvue_account_id,provider_transaction_id,content_item_id)
);

CREATE INDEX provider_purchase_asset_ownership_customer_idx
    ON public.provider_purchase_asset_ownership(fanvue_account_id,external_fanvue_user_uuid,purchase_timestamp);

CREATE TABLE public.schema_migration_checksum_reconciliations (
    reconciliation_id UUID PRIMARY KEY,
    migration_name TEXT NOT NULL,
    prior_checksum TEXT NOT NULL,
    reconciled_checksum TEXT NOT NULL,
    schema_certification_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    reconciled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (migration_name,prior_checksum,reconciled_checksum)
);

COMMIT;
