CREATE TABLE IF NOT EXISTS public.worker_heartbeats (
    heartbeat_id UUID PRIMARY KEY,
    worker_name TEXT NOT NULL,
    worker_instance_id TEXT NOT NULL UNIQUE,
    worker_type TEXT NOT NULL,
    creator_profile_id TEXT NULL,
    account_id BIGINT NULL,
    process_id INTEGER NULL,
    host_name TEXT NOT NULL,
    application_version TEXT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    last_poll_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_failure_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    shutdown_at TIMESTAMPTZ NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT worker_heartbeats_status_check CHECK (
        status IN ('STARTING', 'RUNNING', 'IDLE', 'DEGRADED', 'STOPPING', 'STOPPED', 'FAILED')
    )
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_worker_name
    ON public.worker_heartbeats (worker_name);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_instance
    ON public.worker_heartbeats (worker_instance_id);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_creator_account
    ON public.worker_heartbeats (creator_profile_id, account_id);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_last_heartbeat
    ON public.worker_heartbeats (last_heartbeat_at DESC);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_status
    ON public.worker_heartbeats (status);
