DROP INDEX IF EXISTS public.idx_asset_intelligence_nudenet_work;

ALTER TABLE public.asset_intelligence_profiles
    DROP COLUMN IF EXISTS nudenet_worker_instance_id,
    DROP COLUMN IF EXISTS nudenet_claimed_at,
    DROP COLUMN IF EXISTS nudenet_lease_expires_at,
    DROP COLUMN IF EXISTS nudenet_attempt_count;

ALTER TABLE public.asset_intelligence_profiles
    DROP CONSTRAINT IF EXISTS asset_intelligence_profiles_analysis_status_check;

ALTER TABLE public.asset_intelligence_profiles
    ADD CONSTRAINT asset_intelligence_profiles_analysis_status_check CHECK (
        analysis_status IN ('PENDING', 'ANALYZING', 'READY', 'PARTIAL', 'FAILED')
    );
