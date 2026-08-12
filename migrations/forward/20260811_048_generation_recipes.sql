BEGIN;

CREATE TABLE public.generation_recipes (
  recipe_id UUID PRIMARY KEY,
  schema_version TEXT NOT NULL DEFAULT 'generation_recipe_v1',
  generation_job_id TEXT,
  generation_request_id TEXT NOT NULL,
  prompt_plan_id TEXT,
  submission_index INTEGER NOT NULL CHECK (submission_index >= 0),
  source_workflow TEXT,
  workflow_origin TEXT,
  provider_id TEXT NOT NULL,
  provider_family TEXT,
  provider_adapter TEXT NOT NULL,
  provider_adapter_version TEXT,
  provider_endpoint TEXT,
  provider_model TEXT,
  provider_model_revision TEXT,
  generation_type TEXT NOT NULL,
  media_type TEXT NOT NULL,
  planned_prompt TEXT NOT NULL,
  final_prompt TEXT NOT NULL,
  final_prompt_sha256 TEXT NOT NULL,
  creative_mode TEXT,
  render_policy TEXT,
  render_policy_version TEXT,
  normalized_settings JSONB NOT NULL DEFAULT '{}'::JSONB,
  output_format TEXT,
  width INTEGER,
  height INTEGER,
  aspect_ratio TEXT,
  resolution TEXT,
  seed TEXT,
  seed_policy TEXT NOT NULL CHECK (seed_policy IN ('EXPLICIT','OMITTED_PROVIDER_RANDOM','PROVIDER_MANAGED','UNKNOWN')),
  sanitized_provider_payload JSONB NOT NULL,
  sanitized_payload_sha256 TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (generation_request_id, submission_index)
);

CREATE TABLE public.generation_recipe_references (
  recipe_reference_id UUID PRIMARY KEY,
  recipe_id UUID NOT NULL REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  position INTEGER NOT NULL CHECK (position >= 1),
  role TEXT NOT NULL CHECK (role IN ('CANONICAL_IDENTITY','PHOTOSHOOT_CONTINUITY','EDIT_SOURCE','EDIT_REFERENCE','VIDEO_SOURCE','OTHER')),
  source_type TEXT NOT NULL,
  source_id TEXT,
  asset_id BIGINT,
  generated_image_id TEXT,
  media_type TEXT,
  content_sha256 TEXT,
  provider_reference_kind TEXT,
  diagnostic_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (recipe_id, position)
);

CREATE TABLE public.generation_recipe_executions (
  recipe_id UUID PRIMARY KEY REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  status TEXT NOT NULL CHECK (status IN ('PREPARED','SUBMISSION_STARTED','SUBMITTED','SUBMISSION_REJECTED','SUBMISSION_AMBIGUOUS','WAITING_PROVIDER','SUCCEEDED','FAILED','RESULT_UNKNOWN','CANCELLED')),
  provider_request_id TEXT,
  submission_started_at TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  provider_terminal_status TEXT,
  error_code TEXT,
  error_message TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.generation_recipe_outputs (
  recipe_output_id UUID PRIMARY KEY,
  recipe_id UUID NOT NULL REFERENCES public.generation_recipes(recipe_id) ON DELETE RESTRICT,
  generation_result_id TEXT,
  generated_image_id TEXT,
  output_index INTEGER NOT NULL DEFAULT 0 CHECK (output_index >= 0),
  output_reference_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (recipe_id, output_index)
);

CREATE INDEX idx_generation_recipes_job ON public.generation_recipes(generation_job_id);
CREATE INDEX idx_generation_recipes_request ON public.generation_recipes(generation_request_id);
CREATE INDEX idx_generation_recipe_outputs_image ON public.generation_recipe_outputs(generated_image_id);
CREATE INDEX idx_generation_recipe_executions_provider_request ON public.generation_recipe_executions(provider_request_id);

COMMIT;
