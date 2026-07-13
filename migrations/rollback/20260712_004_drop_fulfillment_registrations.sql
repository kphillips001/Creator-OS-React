DROP TABLE IF EXISTS public.business_asset_fulfillment_history;
DROP TABLE IF EXISTS public.business_asset_fulfillment_registrations;

ALTER TABLE public.commerce_destination_routing_intents
    DROP CONSTRAINT IF EXISTS commerce_destination_routing_status_check;

ALTER TABLE public.commerce_destination_routing_intents
    ADD CONSTRAINT commerce_destination_routing_status_check CHECK (
        routing_status IN (
            'ROUTING_PENDING',
            'ROUTED',
            'ROUTING_FAILED',
            'CANCELLED'
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
