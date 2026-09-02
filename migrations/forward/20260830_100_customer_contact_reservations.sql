BEGIN;

CREATE TABLE public.customer_contact_reservations (
    reservation_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    customer_scope TEXT NOT NULL CHECK (BTRIM(customer_scope) <> ''),
    contact_purpose TEXT NOT NULL CHECK (contact_purpose IN (
        'FREE_ENGAGEMENT','RE_ENGAGEMENT','OUTREACH','DELAYED_FOLLOWUP','MASS_PPV'
    )),
    state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN (
        'ACTIVE','CONFIRMED','FAILED','SEND_UNCERTAIN','EXPIRED','RELEASED'
    )),
    owner_id TEXT NOT NULL CHECK (BTRIM(owner_id) <> ''),
    correlation_id TEXT NULL,
    delivery_reference TEXT NULL,
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at TIMESTAMPTZ NOT NULL,
    finalized_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (lease_expires_at > reserved_at)
);

CREATE UNIQUE INDEX customer_contact_one_active_scope_idx
    ON public.customer_contact_reservations (fanvue_account_id, customer_scope)
    WHERE state IN ('ACTIVE','SEND_UNCERTAIN');

CREATE INDEX customer_contact_expiration_idx
    ON public.customer_contact_reservations (lease_expires_at)
    WHERE state='ACTIVE';

CREATE INDEX customer_contact_history_idx
    ON public.customer_contact_reservations (
        fanvue_account_id, customer_scope, reserved_at DESC
    );

COMMIT;
