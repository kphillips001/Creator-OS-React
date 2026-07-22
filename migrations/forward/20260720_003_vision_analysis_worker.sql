ALTER TABLE public.asset_intelligence_profiles
    ADD COLUMN IF NOT EXISTS vision_worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS vision_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS vision_lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS vision_attempt_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_vision_work
    ON public.asset_intelligence_profiles (analysis_status, vision_lease_expires_at, updated_at);
