ALTER TABLE public.business_asset_registrations
    ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_business_asset_registrations_archive
    ON public.business_asset_registrations (is_archived, archived_at DESC);
