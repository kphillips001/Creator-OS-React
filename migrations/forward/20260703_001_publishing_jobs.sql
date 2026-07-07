BEGIN;

CREATE TABLE IF NOT EXISTS public.publishing_jobs (
    id UUID PRIMARY KEY,
    product_id UUID NULL REFERENCES public.products(id) ON DELETE SET NULL,
    asset_id BIGINT NULL REFERENCES public.content_items(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    provider_account_id BIGINT NULL,
    status TEXT NOT NULL,
    media_link_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED',
    provider_status TEXT NULL,
    provider_output_url TEXT NULL,
    provider_media_id TEXT NULL,
    provider_preview_media_id TEXT NULL,
    provider_full_media_id TEXT NULL,
    provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason TEXT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
    next_retry_at TIMESTAMPTZ NULL,
    upload_started_at TIMESTAMPTZ NULL,
    uploaded_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT publishing_jobs_reference_check CHECK (
        product_id IS NOT NULL OR asset_id IS NOT NULL
    ),
    CONSTRAINT publishing_jobs_status_check CHECK (
        status IN (
            'QUEUED',
            'UPLOADING',
            'UPLOADED',
            'MEDIA_LINK_REQUIRED',
            'MEDIA_LINK_CREATED',
            'COMPLETED',
            'FAILED',
            'RETRY_SCHEDULED',
            'CANCELLED'
        )
    ),
    CONSTRAINT publishing_jobs_media_link_status_check CHECK (
        media_link_status IN (
            'NOT_REQUIRED',
            'REQUIRED',
            'PENDING',
            'CREATED',
            'FAILED'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_publishing_jobs_product
    ON public.publishing_jobs(product_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_publishing_jobs_asset
    ON public.publishing_jobs(asset_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_publishing_jobs_provider_status
    ON public.publishing_jobs(provider, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_publishing_jobs_retry
    ON public.publishing_jobs(next_retry_at)
    WHERE status = 'RETRY_SCHEDULED';

COMMIT;
