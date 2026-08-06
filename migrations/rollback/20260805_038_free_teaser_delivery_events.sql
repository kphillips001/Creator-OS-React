BEGIN;

DROP INDEX IF EXISTS public.uq_photoshoot_lifecycle_provider_delivery;
ALTER TABLE public.customer_photoshoot_lifecycle_events
  DROP COLUMN IF EXISTS provider_delivery_id,
  DROP COLUMN IF EXISTS provider;

COMMIT;
