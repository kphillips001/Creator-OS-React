DROP INDEX IF EXISTS public.idx_photoshoot_deliverables_registration;

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_registration_state_check,
    DROP COLUMN IF EXISTS registration_state;
