BEGIN;

DELETE FROM public.generation_image_dispositions WHERE owner='PHOTOSHOOT';

ALTER TABLE public.generation_image_dispositions
  DROP CONSTRAINT IF EXISTS generation_image_dispositions_owner_check;
ALTER TABLE public.generation_image_dispositions
  ADD CONSTRAINT generation_image_dispositions_owner_check
  CHECK (owner IN ('BUNDLE_STUDIO'));
ALTER TABLE public.generation_image_dispositions
  DROP COLUMN IF EXISTS created_at;
ALTER TABLE public.generation_image_dispositions
  ADD CONSTRAINT generation_image_dispositions_owner_id_fkey
  FOREIGN KEY(owner_id) REFERENCES public.bundle_studio_bundles(bundle_id) ON DELETE CASCADE;

COMMIT;
