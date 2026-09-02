BEGIN;

DROP INDEX IF EXISTS public.idx_generation_library_posting_stage;
ALTER TABLE public.generation_library_read_projection
  DROP COLUMN IF EXISTS staged_at,
  DROP COLUMN IF EXISTS is_staged;
ALTER TABLE public.generation_library_records
  DROP COLUMN IF EXISTS staged_at,
  DROP COLUMN IF EXISTS is_staged;

COMMIT;
