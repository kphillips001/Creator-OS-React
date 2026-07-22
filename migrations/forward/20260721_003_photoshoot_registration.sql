ALTER TABLE public.photoshoot_commerce_deliverables
    ADD COLUMN IF NOT EXISTS registration_state TEXT NOT NULL DEFAULT 'REGISTERED';

ALTER TABLE public.photoshoot_commerce_deliverables
    ALTER COLUMN registration_state SET DEFAULT 'NOT_REGISTERED';

UPDATE public.photoshoot_commerce_deliverables
SET registration_state = 'ARCHIVED'
WHERE is_archived=TRUE AND registration_state='REGISTERED';

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_registration_state_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_deliverable_registration_state_check
    CHECK (registration_state IN ('NOT_REGISTERED', 'REGISTERED', 'ARCHIVED'));

CREATE INDEX IF NOT EXISTS idx_photoshoot_deliverables_registration
    ON public.photoshoot_commerce_deliverables (creator_profile_id, registration_state, is_active, is_archived);
