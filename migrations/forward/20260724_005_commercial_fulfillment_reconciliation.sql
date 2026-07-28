BEGIN;

ALTER TABLE public.commercial_publications
    ADD COLUMN IF NOT EXISTS provider_resource_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    ADD COLUMN IF NOT EXISTS last_reconciled_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS reconciliation_result TEXT NULL;

ALTER TABLE public.commercial_publications
    DROP CONSTRAINT IF EXISTS commercial_publications_provider_resource_status_check;
ALTER TABLE public.commercial_publications
    ADD CONSTRAINT commercial_publications_provider_resource_status_check CHECK (
        provider_resource_status IN (
            'UNVERIFIED', 'PRESENT', 'MISSING', 'MISMATCH', 'AMBIGUOUS'
        )
    );

CREATE INDEX IF NOT EXISTS idx_commercial_publications_fulfillment
    ON public.commercial_publications (
        provider, status, provider_resource_status, published_at DESC
    );

COMMIT;
