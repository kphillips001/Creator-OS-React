ALTER TABLE public.commercial_offerings
    ADD COLUMN IF NOT EXISTS price_minor INTEGER NULL,
    ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'USD';
ALTER TABLE public.commercial_offerings
    DROP CONSTRAINT IF EXISTS commercial_offerings_price_check;
ALTER TABLE public.commercial_offerings
    ADD CONSTRAINT commercial_offerings_price_check
    CHECK (price_minor IS NULL OR price_minor BETWEEN 300 AND 50000);
ALTER TABLE public.commercial_offerings
    DROP CONSTRAINT IF EXISTS commercial_offerings_currency_check;
ALTER TABLE public.commercial_offerings
    ADD CONSTRAINT commercial_offerings_currency_check CHECK (currency='USD');

ALTER TABLE public.commercial_publications
    ADD COLUMN IF NOT EXISTS execution_claim_token UUID NULL,
    ADD COLUMN IF NOT EXISTS execution_lease_expires_at TIMESTAMPTZ NULL;

CREATE TABLE IF NOT EXISTS public.commercial_publication_uploads (
    publication_upload_id UUID PRIMARY KEY,
    publication_id UUID NOT NULL REFERENCES public.commercial_publications(publication_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (provider='FANVUE'),
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    provider_media_uuid TEXT NULL,
    provider_upload_id TEXT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image','video')),
    content_hash TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes>0),
    part_size_bytes BIGINT NULL CHECK (part_size_bytes>0),
    total_parts INTEGER NULL CHECK (total_parts>0),
    uploaded_parts JSONB NOT NULL DEFAULT '{}'::jsonb,
    processing_status TEXT NOT NULL DEFAULT 'pending'
      CHECK (processing_status IN ('pending','processing','ready','error')),
    upload_status TEXT NOT NULL DEFAULT 'pending'
      CHECK (upload_status IN ('pending','uploading','uploaded','failed')),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count>=0),
    last_error TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(publication_id,asset_id,provider)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_publication_upload_provider_media
 ON public.commercial_publication_uploads(provider,fanvue_account_id,provider_media_uuid)
 WHERE provider_media_uuid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_publication_upload_resume
 ON public.commercial_publication_uploads(publication_id,upload_status,processing_status);
