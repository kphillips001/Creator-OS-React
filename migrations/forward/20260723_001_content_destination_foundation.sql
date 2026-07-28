CREATE TABLE IF NOT EXISTS public.asset_content_destinations (
    asset_id BIGINT PRIMARY KEY
        REFERENCES public.content_items(id) ON DELETE CASCADE,
    destination TEXT NOT NULL,
    creator_profile_id INTEGER NULL
        REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    assigned_by_profile_id INTEGER NULL
        REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    source_workflow TEXT NULL,
    source_reference TEXT NULL,
    reason TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_version TEXT NOT NULL DEFAULT 'content_destination_v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT asset_content_destinations_value_check CHECK (
        destination IN (
            'AVAILABLE_INVENTORY',
            'PHOTOSET',
            'VIDEOSET',
            'STORY_SET',
            'TELEGRAM_WALL',
            'TEASER',
            'SINGLE_PPV',
            'BUNDLE'
        )
    )
);

COMMENT ON TABLE public.asset_content_destinations IS
    'Authoritative exactly-one Content Destination per canonical Asset. '
    'Owner=ContentDestinationService.';

CREATE INDEX IF NOT EXISTS idx_asset_content_destinations_destination
    ON public.asset_content_destinations (destination, asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_content_destinations_creator
    ON public.asset_content_destinations (creator_profile_id, destination);

CREATE TABLE IF NOT EXISTS public.asset_content_destination_history (
    history_id BIGSERIAL PRIMARY KEY,
    asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    previous_destination TEXT NULL,
    new_destination TEXT NOT NULL,
    assigned_by_profile_id INTEGER NULL
        REFERENCES public.creator_profiles(id) ON DELETE SET NULL,
    source_workflow TEXT NULL,
    source_reference TEXT NULL,
    reason TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version TEXT NOT NULL DEFAULT 'content_destination_v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT asset_content_destination_history_event_check CHECK (
        event_type IN ('CREATED', 'CHANGED')
    ),
    CONSTRAINT asset_content_destination_history_previous_check CHECK (
        previous_destination IS NULL OR previous_destination IN (
            'AVAILABLE_INVENTORY', 'PHOTOSET', 'VIDEOSET', 'STORY_SET',
            'TELEGRAM_WALL', 'TEASER', 'SINGLE_PPV', 'BUNDLE'
        )
    ),
    CONSTRAINT asset_content_destination_history_new_check CHECK (
        new_destination IN (
            'AVAILABLE_INVENTORY', 'PHOTOSET', 'VIDEOSET', 'STORY_SET',
            'TELEGRAM_WALL', 'TEASER', 'SINGLE_PPV', 'BUNDLE'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_asset_content_destination_history_asset
    ON public.asset_content_destination_history (asset_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.audit_asset_content_destination()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.asset_content_destination_history (
            asset_id, event_type, previous_destination, new_destination,
            assigned_by_profile_id, source_workflow, source_reference,
            reason, metadata, schema_version
        )
        VALUES (
            NEW.asset_id, 'CREATED', NULL, NEW.destination,
            NEW.assigned_by_profile_id, NEW.source_workflow,
            NEW.source_reference, NEW.reason, NEW.metadata,
            NEW.schema_version
        );
    ELSIF OLD.destination IS DISTINCT FROM NEW.destination THEN
        INSERT INTO public.asset_content_destination_history (
            asset_id, event_type, previous_destination, new_destination,
            assigned_by_profile_id, source_workflow, source_reference,
            reason, metadata, schema_version
        )
        VALUES (
            NEW.asset_id, 'CHANGED', OLD.destination, NEW.destination,
            NEW.assigned_by_profile_id, NEW.source_workflow,
            NEW.source_reference, NEW.reason, NEW.metadata,
            NEW.schema_version
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_asset_content_destination
    ON public.asset_content_destinations;
CREATE TRIGGER trg_audit_asset_content_destination
AFTER INSERT OR UPDATE OF destination
ON public.asset_content_destinations
FOR EACH ROW
EXECUTE FUNCTION public.audit_asset_content_destination();

INSERT INTO public.asset_content_destinations (
    asset_id, destination, creator_profile_id, source_workflow,
    source_reference, reason, metadata
)
SELECT
    item.id,
    'AVAILABLE_INVENTORY',
    item.creator_profile_id,
    'content_destination_migration_backfill',
    'content_items:' || item.id::text,
    'Existing canonical Asset initialized as Available Inventory.',
    jsonb_build_object('initialization', 'migration_backfill')
FROM public.content_items item
ON CONFLICT (asset_id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.initialize_content_destination_for_asset()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.asset_content_destinations (
        asset_id, destination, creator_profile_id, source_workflow,
        source_reference, reason, metadata
    )
    VALUES (
        NEW.id,
        'AVAILABLE_INVENTORY',
        NEW.creator_profile_id,
        'canonical_asset_creation',
        'content_items:' || NEW.id::text,
        'Canonical Asset automatically initialized as Available Inventory.',
        jsonb_build_object('initialization', 'content_items_insert_trigger')
    )
    ON CONFLICT (asset_id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_initialize_content_destination
    ON public.content_items;
CREATE TRIGGER trg_initialize_content_destination
AFTER INSERT ON public.content_items
FOR EACH ROW
EXECUTE FUNCTION public.initialize_content_destination_for_asset();

