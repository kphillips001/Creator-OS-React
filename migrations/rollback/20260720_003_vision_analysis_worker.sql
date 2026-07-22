DROP INDEX IF EXISTS public.idx_asset_intelligence_vision_work;

ALTER TABLE public.asset_intelligence_profiles
    DROP COLUMN IF EXISTS vision_worker_instance_id,
    DROP COLUMN IF EXISTS vision_claimed_at,
    DROP COLUMN IF EXISTS vision_lease_expires_at,
    DROP COLUMN IF EXISTS vision_attempt_count;
