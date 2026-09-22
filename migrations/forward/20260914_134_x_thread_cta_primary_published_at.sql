BEGIN;
ALTER TABLE public.x_thread_cta_jobs ADD COLUMN IF NOT EXISTS primary_published_at TIMESTAMPTZ;
UPDATE public.x_thread_cta_jobs job SET primary_published_at=attribution.primary_published_at FROM public.x_link_attributions attribution WHERE job.x_link_attribution_id=attribution.x_link_attribution_id AND job.primary_published_at IS NULL;
ALTER TABLE public.x_thread_cta_jobs ALTER COLUMN primary_published_at SET NOT NULL;
COMMIT;
