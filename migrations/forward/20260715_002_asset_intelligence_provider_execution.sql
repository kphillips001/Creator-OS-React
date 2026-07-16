CREATE TABLE IF NOT EXISTS public.asset_intelligence_runs (
    run_id TEXT PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','READY','PARTIAL','FAILED','CANCELLED')),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    required_providers JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_providers JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_intelligence_runs_current
    ON public.asset_intelligence_runs (asset_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_asset_intelligence_runs_asset_created
    ON public.asset_intelligence_runs (asset_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_asset_intelligence_runs_status
    ON public.asset_intelligence_runs (status);

CREATE TABLE IF NOT EXISTS public.asset_intelligence_provider_executions (
    execution_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES public.asset_intelligence_runs(run_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    is_required BOOLEAN NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','TIMED_OUT','SKIPPED','CANCELLED')),
    result_id TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error_code TEXT CHECK (error_code IS NULL OR error_code IN (
        'CONFIGURATION_ERROR','MEDIA_NOT_FOUND','UNSUPPORTED_MEDIA','AUTHENTICATION_ERROR',
        'RATE_LIMITED','PROVIDER_UNAVAILABLE','PROVIDER_TIMEOUT','INVALID_RESPONSE',
        'NORMALIZATION_ERROR','INTERNAL_ERROR')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, provider_name, attempt_number),
    UNIQUE (result_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_executions_run_provider
    ON public.asset_intelligence_provider_executions (run_id, provider_name, attempt_number DESC);
CREATE INDEX IF NOT EXISTS idx_asset_intelligence_executions_asset_status
    ON public.asset_intelligence_provider_executions (asset_id, status);

ALTER TABLE public.asset_intelligence_provider_results
    ADD COLUMN IF NOT EXISTS run_id TEXT REFERENCES public.asset_intelligence_runs(run_id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS execution_id TEXT REFERENCES public.asset_intelligence_provider_executions(execution_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_intelligence_results_execution
    ON public.asset_intelligence_provider_results (execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_asset_intelligence_results_run
    ON public.asset_intelligence_provider_results (run_id, provider, created_at);

