UPDATE public.photoshoot_commerce_deliverables
SET registration_state='NOT_REGISTERED'
WHERE registration_state IN ('PHOTOSHOOT_COMPLETE', 'IN_ASSET_LIBRARY');

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_registration_state_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_deliverable_registration_state_check
    CHECK (registration_state IN ('NOT_REGISTERED', 'REGISTERED', 'ARCHIVED'));

ALTER TABLE public.photoshoot_commerce_deliverables
    ALTER COLUMN registration_state SET DEFAULT 'NOT_REGISTERED';
