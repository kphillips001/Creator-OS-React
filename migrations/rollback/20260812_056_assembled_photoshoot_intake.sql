BEGIN;
DROP TABLE IF EXISTS public.assembled_photoshoot_intake_members;
DROP TABLE IF EXISTS public.assembled_photoshoot_intakes;
DROP INDEX IF EXISTS public.uq_photoshoot_deliverable_source_reference;
ALTER TABLE public.photoshoot_commerce_deliverables
  DROP COLUMN IF EXISTS source_reference,
  DROP COLUMN IF EXISTS source_kind;
COMMIT;
