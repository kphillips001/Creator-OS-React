BEGIN;

ALTER TABLE public.generation_library_records
  ADD COLUMN IF NOT EXISTS is_staged BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS staged_at TIMESTAMPTZ;

ALTER TABLE public.generation_library_read_projection
  ADD COLUMN IF NOT EXISTS is_staged BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS staged_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_generation_library_posting_stage
  ON public.generation_library_read_projection(
    creator_profile_id, is_staged DESC, staged_at DESC, image_id
  )
  WHERE status = 'active' AND media_available = TRUE;

COMMIT;
