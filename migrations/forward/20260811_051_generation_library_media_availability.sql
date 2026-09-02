BEGIN;
ALTER TABLE public.generation_library_read_projection
  ADD COLUMN media_available BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX idx_generation_library_available_newest
  ON public.generation_library_read_projection(creator_profile_id, generation_date DESC, image_id)
  WHERE status='active' AND media_available=TRUE;
COMMIT;
