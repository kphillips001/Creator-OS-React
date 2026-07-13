CREATE TABLE IF NOT EXISTS public.chat_commerce_registrations (
    chat_registration_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    registration_id UUID NOT NULL REFERENCES public.business_asset_registrations(registration_id) ON DELETE CASCADE,
    fulfillment_id UUID NOT NULL REFERENCES public.business_asset_fulfillment_registrations(fulfillment_id) ON DELETE CASCADE,
    creator_profile_id INTEGER NULL,
    commerce_destination TEXT NULL,
    availability_state TEXT NOT NULL,
    chat_ready BOOLEAN NOT NULL DEFAULT FALSE,
    fulfillment_ready BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    delivery_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    temporarily_unavailable BOOLEAN NOT NULL DEFAULT FALSE,
    retired BOOLEAN NOT NULL DEFAULT FALSE,
    product_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    experience_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_workflow TEXT NULL,
    media_link TEXT NULL,
    provider_media_id TEXT NULL,
    provider TEXT NULL,
    registered_at TIMESTAMPTZ NULL,
    chat_ready_at TIMESTAMPTZ NULL,
    temporarily_unavailable_at TIMESTAMPTZ NULL,
    retired_at TIMESTAMPTZ NULL,
    last_refreshed_at TIMESTAMPTZ NULL,
    registration_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    block_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code TEXT NULL,
    error_message TEXT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_commerce_availability_state_check CHECK (
        availability_state IN (
            'PENDING',
            'BLOCKED',
            'CHAT_READY',
            'TEMPORARILY_UNAVAILABLE',
            'RETIRED',
            'FAILED'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_commerce_registrations_asset
    ON public.chat_commerce_registrations (asset_id);

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registrations_ready
    ON public.chat_commerce_registrations (
        availability_state,
        chat_ready,
        active,
        temporarily_unavailable,
        retired,
        updated_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registrations_creator
    ON public.chat_commerce_registrations (creator_profile_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registrations_product_ids
    ON public.chat_commerce_registrations USING GIN (product_ids);

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registrations_experience_ids
    ON public.chat_commerce_registrations USING GIN (experience_ids);

CREATE TABLE IF NOT EXISTS public.chat_commerce_registration_history (
    history_id BIGSERIAL PRIMARY KEY,
    chat_registration_id UUID NOT NULL REFERENCES public.chat_commerce_registrations(chat_registration_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    availability_state TEXT NOT NULL,
    chat_ready BOOLEAN NOT NULL DEFAULT FALSE,
    block_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registration_history_asset
    ON public.chat_commerce_registration_history (asset_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_commerce_registration_history_registration
    ON public.chat_commerce_registration_history (chat_registration_id, created_at DESC);
