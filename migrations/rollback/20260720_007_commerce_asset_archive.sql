DROP INDEX IF EXISTS public.idx_business_asset_registrations_archive;

ALTER TABLE public.business_asset_registrations
    DROP COLUMN IF EXISTS archived_at,
    DROP COLUMN IF EXISTS is_archived;
