CREATE TABLE IF NOT EXISTS public.content_opportunity_records (
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (record_type, record_id)
);

CREATE INDEX IF NOT EXISTS idx_content_opportunity_records_type
    ON public.content_opportunity_records (record_type);

CREATE INDEX IF NOT EXISTS idx_content_opportunity_records_payload
    ON public.content_opportunity_records USING GIN (payload);
