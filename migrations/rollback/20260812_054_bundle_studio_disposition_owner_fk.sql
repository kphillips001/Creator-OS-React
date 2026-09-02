BEGIN;
ALTER TABLE public.generation_image_dispositions
  DROP CONSTRAINT IF EXISTS generation_image_dispositions_owner_id_fkey;
COMMIT;
