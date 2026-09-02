BEGIN;

CREATE TABLE public.customer_abuse_review_incidents (
    incident_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
    mapping_state TEXT NOT NULL CHECK (mapping_state = 'MAPPED_CUSTOMER'),
    abuse_severity TEXT NOT NULL CHECK (abuse_severity IN ('SEVERE','CRITICAL')),
    abuse_category TEXT NOT NULL CHECK (abuse_category IN ('REPEATED_HOSTILITY','DIRECT_ABUSE','HARASSMENT','THREAT')),
    abuse_reason TEXT NOT NULL CHECK (BTRIM(abuse_reason) <> ''),
    inbound_message_id BIGINT NOT NULL,
    inbound_correlation_id TEXT NOT NULL,
    sanitized_excerpt TEXT NULL,
    buyer_stage_snapshot TEXT NULL,
    value_tier_snapshot TEXT NULL,
    lifetime_spend_minor_snapshot BIGINT NOT NULL DEFAULT 0 CHECK (lifetime_spend_minor_snapshot >= 0),
    review_status TEXT NOT NULL DEFAULT 'OPEN' CHECK (review_status IN ('OPEN','RELEASED','MANUALLY_BLOCKED')),
    interaction_hold_active BOOLEAN NOT NULL DEFAULT TRUE,
    incident_group_key TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1 CHECK (evidence_count > 0),
    last_evidence_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ NULL,
    reviewed_by TEXT NULL,
    review_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (inbound_correlation_id)
);

CREATE UNIQUE INDEX customer_abuse_review_one_open_idx
    ON public.customer_abuse_review_incidents (
        creator_profile_id, fanvue_account_id, fanvue_user_id
    ) WHERE review_status = 'OPEN';
CREATE INDEX customer_abuse_review_telegram_idx
    ON public.customer_abuse_review_incidents (
        creator_profile_id, fanvue_account_id, telegram_user_id, created_at DESC
    );

CREATE TABLE public.operator_notification_operations (
    notification_operation_id UUID PRIMARY KEY,
    notification_type TEXT NOT NULL CHECK (notification_type IN ('CUSTOMER_ABUSE_REVIEW')),
    abuse_incident_id UUID NOT NULL UNIQUE REFERENCES public.customer_abuse_review_incidents(incident_id) ON DELETE RESTRICT,
    destination_chat_id TEXT NULL,
    delivery_correlation_id TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    state TEXT NOT NULL DEFAULT 'AUTHORIZED' CHECK (state IN ('AUTHORIZED','CLAIMED','SENT_CONFIRMED','FAILED')),
    claim_owner TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    attempted_at TIMESTAMPTZ NULL,
    confirmed_at TIMESTAMPTZ NULL,
    provider_message_id TEXT NULL,
    failure_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX operator_notification_recovery_idx
    ON public.operator_notification_operations (state, created_at)
    WHERE state IN ('AUTHORIZED','CLAIMED','FAILED');

COMMIT;
