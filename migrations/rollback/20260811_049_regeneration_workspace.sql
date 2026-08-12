BEGIN;

DROP TABLE IF EXISTS public.regeneration_results;
DROP TABLE IF EXISTS public.regeneration_runs;

ALTER TABLE public.generation_recipes
  DROP COLUMN IF EXISTS regeneration_operation_id,
  DROP COLUMN IF EXISTS source_recipe_id,
  DROP COLUMN IF EXISTS source_generated_image_id;

COMMIT;
