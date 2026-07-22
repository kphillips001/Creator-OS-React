DROP INDEX IF EXISTS public.idx_asset_intelligence_grok_work;

ALTER TABLE public.asset_intelligence_profiles
    DROP COLUMN IF EXISTS grok_worker_instance_id,
    DROP COLUMN IF EXISTS grok_claimed_at,
    DROP COLUMN IF EXISTS grok_lease_expires_at,
    DROP COLUMN IF EXISTS grok_attempt_count;
