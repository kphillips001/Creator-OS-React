CREATE TABLE IF NOT EXISTS public.photoshoot_auto_runs (
    session_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'READY',
    current_plan_index INTEGER NOT NULL DEFAULT 0,
    total_frames INTEGER NOT NULL DEFAULT 0,
    current_request_id TEXT NULL,
    worker_id TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    failure_stage TEXT NULL,
    failed_frame_index INTEGER NULL,
    failed_frame_title TEXT NULL,
    failed_provider TEXT NULL,
    failed_request_id TEXT NULL,
    failed_generation_job_id TEXT NULL,
    started_at TIMESTAMPTZ NULL,
    paused_at TIMESTAMPTZ NULL,
    resumed_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stop_requested BOOLEAN NOT NULL DEFAULT false,
    auto_approve_enabled BOOLEAN NOT NULL DEFAULT true,
    review_mode TEXT NOT NULL DEFAULT 'AUTO_APPROVE',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT photoshoot_auto_run_state_check CHECK (state IN (
        'READY','PREPARING','GENERATING','WAITING_FOR_REVIEW','APPROVING','ADVANCING',
        'PAUSED','FAILED','PLAN_COMPLETE','PHOTOSHOOT_COMPLETE')),
    CONSTRAINT photoshoot_auto_run_review_mode_check CHECK (review_mode IN ('AUTO_APPROVE','MANUAL_REVIEW'))
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_auto_run_claim
    ON public.photoshoot_auto_runs (state, stop_requested, lease_expires_at, updated_at);

