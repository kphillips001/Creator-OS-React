ALTER TABLE public.asset_intelligence_profiles
    DROP CONSTRAINT IF EXISTS asset_intelligence_profiles_analysis_status_check;

ALTER TABLE public.asset_intelligence_profiles
    ADD CONSTRAINT asset_intelligence_profiles_analysis_status_check CHECK (
        analysis_status IN (
            'PENDING', 'NUDENET_RUNNING', 'NUDENET_COMPLETE', 'NUDENET_FAILED',
            'ANALYZING', 'READY', 'PARTIAL', 'FAILED'
        )
    );

ALTER TABLE public.asset_intelligence_profiles
    ADD COLUMN IF NOT EXISTS nudenet_worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS nudenet_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nudenet_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nudenet_attempt_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_nudenet_work
    ON public.asset_intelligence_profiles (analysis_status, nudenet_lease_expires_at, updated_at);
