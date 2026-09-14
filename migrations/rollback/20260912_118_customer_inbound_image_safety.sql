BEGIN;
DROP TABLE IF EXISTS public.telegram_explicit_boundary_events;
DROP TABLE IF EXISTS public.telegram_inbound_media_safety_results;
DROP INDEX IF EXISTS public.telegram_inbound_media_safety_recovery_idx;
ALTER TABLE public.telegram_inbound_media_operations
  DROP CONSTRAINT IF EXISTS telegram_inbound_media_operations_state_check,
  DROP CONSTRAINT IF EXISTS telegram_inbound_media_operations_safety_state_check,
  DROP CONSTRAINT IF EXISTS telegram_inbound_media_operations_solicitation_state_check,
  DROP CONSTRAINT IF EXISTS telegram_inbound_media_operations_response_policy_check,
  DROP COLUMN IF EXISTS partial_failure,
  DROP COLUMN IF EXISTS response_policy,
  DROP COLUMN IF EXISTS solicitation_state,
  DROP COLUMN IF EXISTS safety_state,
  DROP COLUMN IF EXISTS safety_classified_at,
  DROP COLUMN IF EXISTS safety_started_at,
  DROP COLUMN IF EXISTS finalized_at,
  DROP COLUMN IF EXISTS album_finalize_after,
  ADD CONSTRAINT telegram_inbound_media_operations_state_check CHECK (state IN (
    'RECEIVED','DOWNLOADING','DOWNLOADED','VALIDATED','READY_FOR_ANALYSIS',
    'UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED'));
COMMIT;
