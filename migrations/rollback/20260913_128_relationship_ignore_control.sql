BEGIN;

ALTER TABLE public.telegram_sales_delivery_operations
  DROP CONSTRAINT IF EXISTS telegram_sales_delivery_operations_state_check;
UPDATE public.telegram_sales_delivery_operations
SET state = 'FAILED',
    updated_at = NOW()
WHERE state = 'SUPPRESSED';
ALTER TABLE public.telegram_sales_delivery_operations
  ADD CONSTRAINT telegram_sales_delivery_operations_state_check CHECK (state IN (
    'CREATED','RETRYABLE','SENDING','TELEGRAM_ACCEPTED','CONFIRMED','FAILED','AMBIGUOUS'));

DROP TABLE IF EXISTS public.telegram_relationship_ignore_events;
ALTER TABLE public.telegram_relationship_controls
  DROP COLUMN IF EXISTS resume_after_inbound_message_id,
  DROP COLUMN IF EXISTS unignored_by,
  DROP COLUMN IF EXISTS unignored_at,
  DROP COLUMN IF EXISTS ignore_reason,
  DROP COLUMN IF EXISTS ignored_by,
  DROP COLUMN IF EXISTS ignored_at,
  DROP COLUMN IF EXISTS ignore_version,
  DROP COLUMN IF EXISTS communication_disposition;

COMMIT;
