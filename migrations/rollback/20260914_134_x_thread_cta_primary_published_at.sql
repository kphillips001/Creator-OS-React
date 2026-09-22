BEGIN;
ALTER TABLE public.x_thread_cta_jobs DROP COLUMN IF EXISTS primary_published_at;
COMMIT;
