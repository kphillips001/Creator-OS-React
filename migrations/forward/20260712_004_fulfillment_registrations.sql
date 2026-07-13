ALTER TABLE public.business_asset_registrations
    DROP CONSTRAINT IF EXISTS business_asset_registrations_lifecycle_check;

ALTER TABLE public.business_asset_registrations
    ADD CONSTRAINT business_asset_registrations_lifecycle_check CHECK (
        business_lifecycle_state IN (
            'APPROVED',
            'INTELLIGENCE_PENDING',
            'INTELLIGENCE_READY',
            'COMMERCE_REGISTERED',
            'AWAITING_DESTINATION',
            'DESTINATION_SELECTED',
            'ROUTING_PENDING',
            'ROUTED',
            'ROUTING_FAILED',
            'PUBLISHING_READY',
            'AWAITING_UPLOAD',
            'WAITING_FOR_MEDIA_LINK',
            'FULFILLMENT_READY',
            'CHAT_READY',
            'RETIRED'
        )
    );

ALTER TABLE public.commerce_destination_routing_intents
    DROP CONSTRAINT IF EXISTS commerce_destination_routing_status_check;

ALTER TABLE public.commerce_destination_routing_intents
    ADD CONSTRAINT commerce_destination_routing_status_check CHECK (
        routing_status IN (
            'ROUTING_PENDING',
            'ROUTING',
            'UPLOAD_IN_PROGRESS',
            'WAITING_FOR_MEDIA_LINK',
            'FULFILLMENT_READY',
            'ROUTED',
            'ROUTING_FAILED',
            'CANCELLED'
        )
    );

CREATE TABLE IF NOT EXISTS public.business_asset_fulfillment_registrations (
    fulfillment_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    registration_id UUID NOT NULL REFERENCES public.business_asset_registrations(registration_id) ON DELETE CASCADE,
    routing_intent_id UUID NOT NULL REFERENCES public.commerce_destination_routing_intents(routing_intent_id) ON DELETE CASCADE,
    route TEXT NOT NULL,
    route_owner TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_account_id INTEGER NULL,
    publishing_job_id UUID NULL REFERENCES public.publishing_jobs(id) ON DELETE SET NULL,
    upload_attempt_id TEXT NULL,
    provider_media_id TEXT NULL,
    provider_preview_media_id TEXT NULL,
    provider_full_media_id TEXT NULL,
    provider_processing_status TEXT NULL,
    lifecycle_state TEXT NOT NULL,
    media_link TEXT NULL,
    media_link_verification_state TEXT NOT NULL,
    media_link_submitted_at TIMESTAMPTZ NULL,
    media_link_verified_at TIMESTAMPTZ NULL,
    fulfillment_ready_at TIMESTAMPTZ NULL,
    failure_code TEXT NULL,
    failure_message TEXT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    retry_required BOOLEAN NOT NULL DEFAULT FALSE,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT business_asset_fulfillment_route_check CHECK (
        route IN ('CUSTOMER_CONVERSATIONS')
    ),
    CONSTRAINT business_asset_fulfillment_owner_check CHECK (
        route_owner IN ('CUSTOMER_CONVERSATIONS')
    ),
    CONSTRAINT business_asset_fulfillment_lifecycle_check CHECK (
        lifecycle_state IN (
            'ROUTING_PENDING',
            'READY_FOR_UPLOAD',
            'UPLOAD_QUEUED',
            'UPLOADING',
            'UPLOADED',
            'PROCESSING',
            'MEDIA_READY',
            'WAITING_FOR_MEDIA_LINK',
            'MEDIA_LINK_SUBMITTED',
            'MEDIA_LINK_VERIFIED',
            'FULFILLMENT_READY',
            'FAILED',
            'RETRY_REQUIRED',
            'RETIRED'
        )
    ),
    CONSTRAINT business_asset_fulfillment_media_link_check CHECK (
        media_link_verification_state IN (
            'NOT_REQUIRED',
            'MISSING',
            'SUBMITTED',
            'VERIFIED',
            'FAILED'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_business_asset_fulfillment_asset_route
    ON public.business_asset_fulfillment_registrations (asset_id, route);

CREATE INDEX IF NOT EXISTS idx_business_asset_fulfillment_route_intent
    ON public.business_asset_fulfillment_registrations (routing_intent_id);

CREATE INDEX IF NOT EXISTS idx_business_asset_fulfillment_job
    ON public.business_asset_fulfillment_registrations (publishing_job_id);

CREATE INDEX IF NOT EXISTS idx_business_asset_fulfillment_state
    ON public.business_asset_fulfillment_registrations (lifecycle_state, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_business_asset_fulfillment_media_link
    ON public.business_asset_fulfillment_registrations (media_link)
    WHERE media_link IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.business_asset_fulfillment_history (
    history_id BIGSERIAL PRIMARY KEY,
    fulfillment_id UUID NOT NULL REFERENCES public.business_asset_fulfillment_registrations(fulfillment_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    route TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    media_link_verification_state TEXT NOT NULL,
    publishing_job_id UUID NULL,
    provider_media_id TEXT NULL,
    failure_code TEXT NULL,
    failure_message TEXT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_business_asset_fulfillment_history_asset
    ON public.business_asset_fulfillment_history (asset_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_business_asset_fulfillment_history_fulfillment
    ON public.business_asset_fulfillment_history (fulfillment_id, created_at DESC);
