BEGIN;

ALTER TABLE public.generation_recipes
  ADD COLUMN source_generated_image_id TEXT,
  ADD COLUMN source_recipe_id UUID REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  ADD COLUMN regeneration_operation_id UUID REFERENCES public.background_operations(operation_id) ON DELETE RESTRICT;

CREATE TABLE public.regeneration_runs (
  operation_id UUID PRIMARY KEY REFERENCES public.background_operations(operation_id) ON DELETE RESTRICT,
  creator_profile_id BIGINT NOT NULL,
  source_generated_image_id TEXT NOT NULL,
  source_recipe_id UUID NOT NULL REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  requested_count INTEGER NOT NULL CHECK (requested_count BETWEEN 1 AND 5),
  status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.regeneration_results (
  regeneration_result_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL REFERENCES public.regeneration_runs(operation_id) ON DELETE RESTRICT,
  variation_index INTEGER NOT NULL CHECK (variation_index BETWEEN 1 AND 5),
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','SUBMISSION_AMBIGUOUS')),
  generation_job_id TEXT,
  generation_result_id TEXT,
  generated_image_id TEXT,
  generation_recipe_id UUID REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  media_path TEXT,
  disposition TEXT NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (disposition IN ('PENDING_REVIEW','PROMOTED','ARCHIVED')),
  error_code TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (operation_id, variation_index)
);

CREATE INDEX idx_generation_recipes_source_recipe ON public.generation_recipes(source_recipe_id);
CREATE INDEX idx_generation_recipes_regeneration_operation ON public.generation_recipes(regeneration_operation_id);
CREATE INDEX idx_regeneration_runs_source_image ON public.regeneration_runs(source_generated_image_id);
CREATE INDEX idx_regeneration_results_operation ON public.regeneration_results(operation_id, variation_index);
CREATE UNIQUE INDEX uq_regeneration_results_generated_image ON public.regeneration_results(generated_image_id) WHERE generated_image_id IS NOT NULL;

COMMIT;
