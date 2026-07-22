DROP INDEX IF EXISTS public.idx_asset_intelligence_content_merge_work;

ALTER TABLE public.asset_intelligence_profiles
    DROP COLUMN IF EXISTS content_merge_worker_instance_id,
    DROP COLUMN IF EXISTS content_merge_claimed_at,
    DROP COLUMN IF EXISTS content_merge_lease_expires_at,
    DROP COLUMN IF EXISTS content_merge_attempt_count;
