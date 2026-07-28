CREATE TABLE IF NOT EXISTS public.commercial_publications (
    publication_id UUID PRIMARY KEY,
    commercial_offering_id UUID NOT NULL
        REFERENCES public.commercial_offerings(offering_id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('FANVUE')),
    status TEXT NOT NULL CHECK (
        status IN ('DRAFT','READY_TO_PUBLISH','PUBLISHING','LIVE','FAILED','ARCHIVED')
    ),
    external_product_id TEXT NULL,
    published_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    publication_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (commercial_offering_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_commercial_publications_offering
    ON public.commercial_publications (commercial_offering_id, created_at);
CREATE INDEX IF NOT EXISTS idx_commercial_publications_provider_status
    ON public.commercial_publications (provider, status, updated_at);
