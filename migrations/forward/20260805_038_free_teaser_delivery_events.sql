BEGIN;

ALTER TABLE public.customer_photoshoot_lifecycle_events
  ADD COLUMN IF NOT EXISTS provider TEXT,
  ADD COLUMN IF NOT EXISTS provider_delivery_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_photoshoot_lifecycle_provider_delivery
  ON public.customer_photoshoot_lifecycle_events
    (lifecycle_id, event_type, asset_id, provider, provider_delivery_id)
  WHERE provider_delivery_id IS NOT NULL;

COMMIT;
