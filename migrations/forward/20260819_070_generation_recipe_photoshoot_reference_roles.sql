BEGIN;

ALTER TABLE public.generation_recipe_references
  DROP CONSTRAINT generation_recipe_references_role_check;

ALTER TABLE public.generation_recipe_references
  ADD CONSTRAINT generation_recipe_references_role_check
  CHECK (role IN (
    'CANONICAL_IDENTITY',
    'PHOTOSHOOT_CONTINUITY',
    'ORIGINAL_PHOTOSHOOT_SEED',
    'PREVIOUS_APPROVED_CONTINUITY',
    'EDIT_SOURCE',
    'EDIT_REFERENCE',
    'VIDEO_SOURCE',
    'OTHER'
  ));

COMMIT;
