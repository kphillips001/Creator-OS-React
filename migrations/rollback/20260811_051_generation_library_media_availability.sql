BEGIN;
DROP INDEX IF EXISTS public.idx_generation_library_available_newest;
ALTER TABLE public.generation_library_read_projection DROP COLUMN IF EXISTS media_available;
COMMIT;
