CREATE TABLE IF NOT EXISTS public.ready_asset_chat_registration_jobs (
    asset_id BIGINT PRIMARY KEY REFERENCES public.content_items(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    worker_instance_id TEXT,
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    chat_registration_id UUID,
    availability_state TEXT,
    missing_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_code TEXT,
    error_message TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ready_asset_chat_registration_jobs_status_check
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETE', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_ready_asset_chat_registration_jobs_claim
    ON public.ready_asset_chat_registration_jobs (status, lease_expires_at, updated_at);
