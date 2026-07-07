CREATE TABLE IF NOT EXISTS public.runtime_control_records (
    creator_profile_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL DEFAULT 'OFFLINE',
    status TEXT NOT NULL DEFAULT 'OFFLINE',
    current_runtime_provider TEXT NOT NULL DEFAULT 'telegram',
    last_started TIMESTAMPTZ NULL,
    last_stopped TIMESTAMPTZ NULL,
    active_conversations INTEGER NOT NULL DEFAULT 0 CHECK (active_conversations >= 0),
    pending_deliveries INTEGER NOT NULL DEFAULT 0 CHECK (pending_deliveries >= 0),
    pending_offers INTEGER NOT NULL DEFAULT 0 CHECK (pending_offers >= 0),
    observed_recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_control_records_mode_check CHECK (
        mode IN ('OFFLINE', 'OBSERVE', 'LIVE')
    ),
    CONSTRAINT runtime_control_records_status_check CHECK (
        status IN ('OFFLINE', 'OBSERVE', 'LIVE')
    )
);

CREATE INDEX IF NOT EXISTS idx_runtime_control_records_mode
    ON public.runtime_control_records (mode);

CREATE INDEX IF NOT EXISTS idx_runtime_control_records_updated_at
    ON public.runtime_control_records (updated_at DESC);
