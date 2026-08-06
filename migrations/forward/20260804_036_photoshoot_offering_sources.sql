ALTER TABLE public.commercial_offerings
    ADD COLUMN IF NOT EXISTS source_photoshoot_deliverable_id UUID NULL
        REFERENCES public.photoshoot_commerce_deliverables(deliverable_id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_commercial_offerings_creator_idempotency
    ON public.commercial_offerings (creator_profile_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_commercial_offerings_source_photoshoot
    ON public.commercial_offerings (source_photoshoot_deliverable_id);
