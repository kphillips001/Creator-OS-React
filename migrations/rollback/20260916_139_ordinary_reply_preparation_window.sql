BEGIN;

DROP INDEX IF EXISTS public.idx_ordinary_reply_preparation_due;

ALTER TABLE public.ordinary_chat_reply_operations
  DROP COLUMN IF EXISTS preparation_eligible_at,
  DROP COLUMN IF EXISTS scheduled_delivery_at;

COMMIT;
