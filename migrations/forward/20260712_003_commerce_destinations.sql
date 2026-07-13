ALTER TABLE public.business_asset_registrations
    ADD COLUMN IF NOT EXISTS selected_commerce_destination TEXT NULL,
    ADD COLUMN IF NOT EXISTS destination_selected_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS destination_selected_by_profile_id INTEGER NULL REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS destination_source_workflow TEXT NULL,
    ADD COLUMN IF NOT EXISTS destination_routing_state TEXT NULL,
    ADD COLUMN IF NOT EXISTS destination_change_note TEXT NULL,
    ADD COLUMN IF NOT EXISTS destination_revision INTEGER NOT NULL DEFAULT 0;

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
            'CHAT_READY',
            'RETIRED'
        )
    );

ALTER TABLE public.business_asset_registrations
    DROP CONSTRAINT IF EXISTS business_asset_registrations_destination_check;

ALTER TABLE public.business_asset_registrations
    ADD CONSTRAINT business_asset_registrations_destination_check CHECK (
        commerce_destination_status IN (
            'NOT_READY',
            'AWAITING_DESTINATION',
            'DESTINATION_SELECTED',
            'ROUTING_PENDING',
            'ROUTED',
            'ROUTING_FAILED'
        )
    );

ALTER TABLE public.business_asset_registrations
    DROP CONSTRAINT IF EXISTS business_asset_registrations_selected_destination_check;

ALTER TABLE public.business_asset_registrations
    ADD CONSTRAINT business_asset_registrations_selected_destination_check CHECK (
        selected_commerce_destination IS NULL
        OR selected_commerce_destination IN (
            'TELEGRAM_WALL',
            'CUSTOMER_CONVERSATIONS',
            'BOTH',
            'ARCHIVE_ONLY'
        )
    );

CREATE TABLE IF NOT EXISTS public.commerce_destination_history (
    history_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    registration_id UUID NOT NULL REFERENCES public.business_asset_registrations(registration_id) ON DELETE CASCADE,
    previous_destination TEXT NULL,
    new_destination TEXT NULL,
    creator_profile_id INTEGER NULL REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    creator_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_workflow TEXT NULL,
    source_session_id TEXT NULL,
    reason TEXT NULL,
    idempotency_key TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT commerce_destination_history_previous_destination_check CHECK (
        previous_destination IS NULL
        OR previous_destination IN (
            'TELEGRAM_WALL',
            'CUSTOMER_CONVERSATIONS',
            'BOTH',
            'ARCHIVE_ONLY'
        )
    ),
    CONSTRAINT commerce_destination_history_new_destination_check CHECK (
        new_destination IS NULL
        OR new_destination IN (
            'TELEGRAM_WALL',
            'CUSTOMER_CONVERSATIONS',
            'BOTH',
            'ARCHIVE_ONLY'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_commerce_destination_history_asset
    ON public.commerce_destination_history (asset_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_commerce_destination_history_idempotency
    ON public.commerce_destination_history (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.commerce_destination_routing_intents (
    routing_intent_id UUID PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    registration_id UUID NOT NULL REFERENCES public.business_asset_registrations(registration_id) ON DELETE CASCADE,
    selected_destination TEXT NOT NULL,
    routing_owner TEXT NOT NULL,
    routing_status TEXT NOT NULL,
    source_workflow TEXT NULL,
    downstream_owner_service TEXT NULL,
    downstream_prerequisites JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT commerce_destination_routing_selected_destination_check CHECK (
        selected_destination IN (
            'TELEGRAM_WALL',
            'CUSTOMER_CONVERSATIONS',
            'BOTH',
            'ARCHIVE_ONLY'
        )
    ),
    CONSTRAINT commerce_destination_routing_owner_check CHECK (
        routing_owner IN (
            'TELEGRAM_WALL',
            'CUSTOMER_CONVERSATIONS',
            'ARCHIVE'
        )
    ),
    CONSTRAINT commerce_destination_routing_status_check CHECK (
        routing_status IN (
            'ROUTING_PENDING',
            'ROUTED',
            'ROUTING_FAILED',
            'CANCELLED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_commerce_destination_routing_asset
    ON public.commerce_destination_routing_intents (asset_id, routing_owner);

CREATE INDEX IF NOT EXISTS idx_commerce_destination_routing_status
    ON public.commerce_destination_routing_intents (routing_status, created_at);

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_selected_destination
    ON public.business_asset_registrations (
        selected_commerce_destination,
        commerce_destination_status
    );
