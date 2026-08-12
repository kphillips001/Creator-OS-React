DROP INDEX IF EXISTS public.idx_publication_upload_provider_media;
CREATE INDEX IF NOT EXISTS idx_publication_upload_provider_media
 ON public.commercial_publication_uploads(provider,fanvue_account_id,provider_media_uuid)
 WHERE provider_media_uuid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_publication_upload_asset_revision
 ON public.commercial_publication_uploads(
   provider,fanvue_account_id,asset_id,content_hash,file_size_bytes
 ) WHERE upload_status='uploaded' AND processing_status='ready';
