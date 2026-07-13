CREATE TABLE IF NOT EXISTS public.business_asset_registrations (
    registration_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL UNIQUE REFERENCES public.content_items(id) ON DELETE CASCADE,
    creator_profile_id INTEGER NULL REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    approval_status TEXT NOT NULL,
    content_intelligence_status TEXT NOT NULL,
    content_intelligence_ready BOOLEAN NOT NULL DEFAULT FALSE,
    commerce_registration_status TEXT NOT NULL,
    business_lifecycle_state TEXT NOT NULL,
    commerce_destination_status TEXT NOT NULL,
    product_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    experience_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    product_draft_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    delivery_type TEXT NULL,
    delivery_type_source TEXT NULL,
    delivery_type_requires_review BOOLEAN NOT NULL DEFAULT FALSE,
    commerce_intelligence_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
    publishing_readiness JSONB NOT NULL DEFAULT '{}'::jsonb,
    fulfillment_readiness JSONB NOT NULL DEFAULT '{}'::jsonb,
    relationship_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    registration_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code TEXT NULL,
    error_message TEXT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    registered_at TIMESTAMPTZ NULL,
    last_refreshed_at TIMESTAMPTZ NULL,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT business_asset_registrations_status_check CHECK (
        commerce_registration_status IN ('PENDING', 'REGISTERED', 'BLOCKED', 'FAILED', 'RETIRED')
    ),
    CONSTRAINT business_asset_registrations_lifecycle_check CHECK (
        business_lifecycle_state IN (
            'APPROVED',
            'INTELLIGENCE_PENDING',
            'INTELLIGENCE_READY',
            'COMMERCE_REGISTERED',
            'AWAITING_DESTINATION',
            'PUBLISHING_READY',
            'AWAITING_UPLOAD',
            'WAITING_FOR_MEDIA_LINK',
            'CHAT_READY',
            'RETIRED'
        )
    ),
    CONSTRAINT business_asset_registrations_destination_check CHECK (
        commerce_destination_status IN ('NOT_READY', 'AWAITING_DESTINATION', 'DESTINATION_SELECTED')
    )
);

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_creator_profile
    ON public.business_asset_registrations (creator_profile_id);

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_status_lifecycle
    ON public.business_asset_registrations (
        commerce_registration_status,
        business_lifecycle_state,
        commerce_destination_status
    );

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_product_ids
    ON public.business_asset_registrations USING GIN (product_ids);

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_experience_ids
    ON public.business_asset_registrations USING GIN (experience_ids);
