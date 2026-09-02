BEGIN;

ALTER TABLE public.bundle_studio_bundles DROP CONSTRAINT IF EXISTS bundle_studio_bundles_status_check;
ALTER TABLE public.bundle_studio_bundles ADD CONSTRAINT bundle_studio_bundles_status_check
  CHECK (status IN ('ACTIVE','PREPARING','READY','ABANDONED','COMPLETED'));
ALTER TABLE public.bundle_studio_bundles
  ADD COLUMN IF NOT EXISTS sales_destination TEXT NULL CHECK (sales_destination IN ('CHAT','CONTENT_WALL')),
  ADD COLUMN IF NOT EXISTS commercial_offering_id UUID NULL REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT;

ALTER TABLE public.commercial_offerings
  ADD COLUMN IF NOT EXISTS source_bundle_studio_bundle_id UUID NULL
    REFERENCES public.bundle_studio_bundles(bundle_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_commercial_offerings_bundle_studio_source
  ON public.commercial_offerings(source_bundle_studio_bundle_id)
  WHERE source_bundle_studio_bundle_id IS NOT NULL AND status <> 'ARCHIVED';

CREATE TABLE IF NOT EXISTS public.bundle_studio_teasers (
  bundle_id UUID PRIMARY KEY REFERENCES public.bundle_studio_bundles(bundle_id) ON DELETE CASCADE,
  creator_profile_id INTEGER NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
  source_asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
  teaser_asset_id BIGINT NOT NULL UNIQUE REFERENCES public.content_items(id) ON DELETE RESTRICT,
  commercial_role TEXT NOT NULL DEFAULT 'BUNDLE_PROMOTIONAL_TEASER' CHECK (commercial_role='BUNDLE_PROMOTIONAL_TEASER'),
  mask_path TEXT NOT NULL, mask_width INTEGER NOT NULL CHECK (mask_width BETWEEN 1 AND 2048),
  mask_height INTEGER NOT NULL CHECK (mask_height BETWEEN 1 AND 2048),
  mask_version TEXT NOT NULL DEFAULT 'selective_blur_mask_v1',
  blur_strength INTEGER NOT NULL CHECK (blur_strength BETWEEN 1 AND 80),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
