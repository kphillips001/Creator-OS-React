BEGIN;
DROP TABLE IF EXISTS public.bundle_studio_teasers;
DROP INDEX IF EXISTS public.uq_commercial_offerings_bundle_studio_source;
ALTER TABLE public.commercial_offerings DROP COLUMN IF EXISTS source_bundle_studio_bundle_id;
ALTER TABLE public.bundle_studio_bundles DROP COLUMN IF EXISTS commercial_offering_id, DROP COLUMN IF EXISTS sales_destination;
ALTER TABLE public.bundle_studio_bundles DROP CONSTRAINT IF EXISTS bundle_studio_bundles_status_check;
ALTER TABLE public.bundle_studio_bundles ADD CONSTRAINT bundle_studio_bundles_status_check CHECK (status IN ('ACTIVE','ABANDONED','COMPLETED'));
COMMIT;
