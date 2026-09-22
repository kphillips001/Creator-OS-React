BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.ordinary_chat_reply_operations
     WHERE operation_kind='HISTORICAL_CORRECTIVE'
  ) THEN
    RAISE EXCEPTION 'Rollback blocked: historical corrective operations exist.';
  END IF;
END $$;

DROP INDEX IF EXISTS public.ix_ordinary_reply_recovery_cause;
DROP INDEX IF EXISTS public.uq_ordinary_reply_recovery_idempotency;
DROP INDEX IF EXISTS public.uq_ordinary_reply_primary_inbound;

ALTER TABLE public.ordinary_chat_reply_operations
  DROP CONSTRAINT IF EXISTS ordinary_reply_recovery_identity_check,
  DROP COLUMN IF EXISTS recovery_idempotency_key,
  DROP COLUMN IF EXISTS recovery_resolution_plan_id,
  DROP COLUMN IF EXISTS recovery_attention_occurrence_id,
  DROP COLUMN IF EXISTS causal_operation_id,
  DROP COLUMN IF EXISTS operation_kind;

ALTER TABLE public.ordinary_chat_reply_operations
  ADD CONSTRAINT ordinary_chat_reply_operation_telegram_account_scope_telegr_key
  UNIQUE (telegram_account_scope,telegram_chat_id,inbound_telegram_message_id);

COMMIT;
