DROP TABLE IF EXISTS public.commerce_destination_routing_intents;
DROP TABLE IF EXISTS public.commerce_destination_history;

DROP INDEX IF EXISTS public.idx_business_asset_registrations_selected_destination;

ALTER TABLE public.business_asset_registrations
    DROP CONSTRAINT IF EXISTS business_asset_registrations_selected_destination_check;

ALTER TABLE public.business_asset_registrations
    DROP CONSTRAINT IF EXISTS business_asset_registrations_destination_check;

ALTER TABLE public.business_asset_registrations
    ADD CONSTRAINT business_asset_registrations_destination_check CHECK (
        commerce_destination_status IN (
            'NOT_READY',
            'AWAITING_DESTINATION',
            'DESTINATION_SELECTED'
        )
    );

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
            'PUBLISHING_READY',
            'AWAITING_UPLOAD',
            'WAITING_FOR_MEDIA_LINK',
            'CHAT_READY',
            'RETIRED'
        )
    );

ALTER TABLE public.business_asset_registrations
    DROP COLUMN IF EXISTS selected_commerce_destination,
    DROP COLUMN IF EXISTS destination_selected_at,
    DROP COLUMN IF EXISTS destination_selected_by_profile_id,
    DROP COLUMN IF EXISTS destination_source_workflow,
    DROP COLUMN IF EXISTS destination_routing_state,
    DROP COLUMN IF EXISTS destination_change_note,
    DROP COLUMN IF EXISTS destination_revision;
