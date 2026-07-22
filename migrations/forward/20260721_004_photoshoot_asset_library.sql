ALTER TABLE public.photoshoot_commerce_deliverables
    ALTER COLUMN registration_state SET DEFAULT 'PHOTOSHOOT_COMPLETE';

UPDATE public.photoshoot_commerce_deliverables
SET registration_state='PHOTOSHOOT_COMPLETE'
WHERE registration_state='NOT_REGISTERED';

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_registration_state_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_deliverable_registration_state_check
    CHECK (registration_state IN ('PHOTOSHOOT_COMPLETE', 'IN_ASSET_LIBRARY', 'REGISTERED', 'ARCHIVED'));
