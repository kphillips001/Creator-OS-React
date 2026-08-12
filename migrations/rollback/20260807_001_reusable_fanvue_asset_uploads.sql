DROP INDEX IF EXISTS public.idx_publication_upload_asset_revision;
DROP INDEX IF EXISTS public.idx_publication_upload_provider_media;
CREATE UNIQUE INDEX IF NOT EXISTS idx_publication_upload_provider_media
 ON public.commercial_publication_uploads(provider,fanvue_account_id,provider_media_uuid)
 WHERE provider_media_uuid IS NOT NULL;
