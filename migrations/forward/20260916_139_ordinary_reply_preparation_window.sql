BEGIN;

ALTER TABLE public.ordinary_chat_reply_operations
  ADD COLUMN IF NOT EXISTS scheduled_delivery_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS preparation_eligible_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_ordinary_reply_preparation_due
  ON public.ordinary_chat_reply_operations (
    telegram_account_scope, preparation_eligible_at, inbound_received_at
  )
  WHERE state='RETRYABLE' AND response_payload IS NULL
    AND preparation_eligible_at IS NOT NULL;

COMMIT;
