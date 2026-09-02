DROP TABLE IF EXISTS public.telegram_identity_verification_audit;
DROP TABLE IF EXISTS public.telegram_identity_observations;
DROP INDEX IF EXISTS public.idx_telegram_identity_verification_status;
ALTER TABLE public.telegram_identity_map
    DROP CONSTRAINT IF EXISTS telegram_identity_map_verification_status_check,
    DROP COLUMN IF EXISTS last_observed_display_name,
    DROP COLUMN IF EXISTS last_observed_username,
    DROP COLUMN IF EXISTS verification_evidence,
    DROP COLUMN IF EXISTS verified_by,
    DROP COLUMN IF EXISTS verified_at,
    DROP COLUMN IF EXISTS verification_method,
    DROP COLUMN IF EXISTS verification_status;
