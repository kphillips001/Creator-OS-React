BEGIN;

CREATE TABLE public.external_customer_identity_observations (
    observation_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    platform TEXT NOT NULL CHECK (platform IN ('X')),
    external_numeric_id TEXT NOT NULL CHECK (external_numeric_id ~ '^[0-9]+$'),
    observed_username TEXT NULL,
    observed_display_name TEXT NULL,
    observation_source TEXT NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id, platform, external_numeric_id)
);

CREATE TABLE public.canonical_customer_materialization_audit (
    audit_id UUID PRIMARY KEY,
    customer_commerce_profile_id UUID NOT NULL REFERENCES public.customer_commerce_profiles(customer_commerce_profile_id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CREATED','METADATA_COMPLETED')),
    source TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.verified_external_customer_identities (
    external_identity_link_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    platform TEXT NOT NULL CHECK (platform IN ('X')),
    external_numeric_id TEXT NOT NULL CHECK (external_numeric_id ~ '^[0-9]+$'),
    observation_id UUID NOT NULL REFERENCES public.external_customer_identity_observations(observation_id) ON DELETE RESTRICT,
    observed_username TEXT NULL,
    observed_display_name TEXT NULL,
    verification_method TEXT NOT NULL,
    verification_source TEXT NOT NULL,
    verification_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    deactivated_at TIMESTAMPTZ NULL,
    deactivation_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX verified_external_customer_identity_active_external_idx
ON public.verified_external_customer_identities(creator_profile_id,platform,external_numeric_id)
WHERE is_active;

CREATE UNIQUE INDEX verified_external_customer_identity_active_customer_idx
ON public.verified_external_customer_identities(
    creator_profile_id,fanvue_account_id,local_fanvue_user_id,platform
) WHERE is_active;

CREATE TABLE public.verified_external_customer_identity_audit (
    audit_id UUID PRIMARY KEY,
    external_identity_link_id UUID NOT NULL REFERENCES public.verified_external_customer_identities(external_identity_link_id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action IN ('VERIFIED','METADATA_REFRESHED','DEACTIVATED')),
    operator_source TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
