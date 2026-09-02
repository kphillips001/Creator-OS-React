BEGIN;
ALTER TABLE public.generation_image_dispositions
  ADD CONSTRAINT generation_image_dispositions_owner_id_fkey
  FOREIGN KEY(owner_id) REFERENCES public.bundle_studio_bundles(bundle_id) ON DELETE CASCADE;
COMMIT;
