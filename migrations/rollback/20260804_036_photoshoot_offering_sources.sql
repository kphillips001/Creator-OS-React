DROP INDEX IF EXISTS public.idx_commercial_offerings_source_photoshoot;
DROP INDEX IF EXISTS public.idx_commercial_offerings_creator_idempotency;
ALTER TABLE public.commercial_offerings
    DROP COLUMN IF EXISTS idempotency_key,
    DROP COLUMN IF EXISTS source_photoshoot_deliverable_id;
