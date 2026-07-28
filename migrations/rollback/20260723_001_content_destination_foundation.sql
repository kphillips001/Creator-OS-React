DROP TRIGGER IF EXISTS trg_initialize_content_destination
    ON public.content_items;
DROP FUNCTION IF EXISTS public.initialize_content_destination_for_asset();

DROP TRIGGER IF EXISTS trg_audit_asset_content_destination
    ON public.asset_content_destinations;
DROP FUNCTION IF EXISTS public.audit_asset_content_destination();

DROP TABLE IF EXISTS public.asset_content_destination_history;
DROP TABLE IF EXISTS public.asset_content_destinations;

