BEGIN;

CREATE TABLE public.generation_library_read_projection (
  image_id TEXT PRIMARY KEY,
  generation_job_id TEXT NOT NULL,
  output_reference TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL,
  provider_id TEXT NOT NULL,
  prompt_plan_id TEXT NOT NULL DEFAULT '',
  prompt_text TEXT NOT NULL DEFAULT '',
  creative_mode TEXT,
  reference_asset_id BIGINT,
  generation_recipe_id UUID,
  photoshoot_session_id TEXT,
  generation_date TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL,
  review_state TEXT NOT NULL,
  selected BOOLEAN NOT NULL DEFAULT FALSE,
  imported_asset_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ
);

CREATE INDEX idx_generation_library_browse_newest
  ON public.generation_library_read_projection(creator_profile_id, status, generation_date DESC, image_id);
CREATE INDEX idx_generation_library_browse_provider
  ON public.generation_library_read_projection(creator_profile_id, status, provider_id, generation_date DESC);
CREATE INDEX idx_generation_library_browse_mode
  ON public.generation_library_read_projection(creator_profile_id, status, creative_mode, generation_date DESC);
CREATE INDEX idx_generation_library_staged
  ON public.generation_library_read_projection(creator_profile_id, generation_date DESC)
  WHERE status='staged_asset_library';
CREATE INDEX idx_generation_library_photoshoot
  ON public.generation_library_read_projection(photoshoot_session_id, generation_date DESC)
  WHERE photoshoot_session_id IS NOT NULL;

CREATE TABLE public.generation_library_projection_state (
  projection_name TEXT PRIMARY KEY,
  source_version TEXT NOT NULL,
  projected_count INTEGER NOT NULL,
  synchronized_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
