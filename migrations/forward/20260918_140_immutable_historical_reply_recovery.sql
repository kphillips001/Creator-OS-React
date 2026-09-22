BEGIN;

ALTER TABLE public.ordinary_chat_reply_operations
  ADD COLUMN operation_kind TEXT NOT NULL DEFAULT 'PRIMARY'
    CHECK (operation_kind IN ('PRIMARY','HISTORICAL_CORRECTIVE')),
  ADD COLUMN causal_operation_id UUID NULL
    REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE RESTRICT,
  ADD COLUMN recovery_attention_occurrence_id TEXT NULL,
  ADD COLUMN recovery_resolution_plan_id UUID NULL,
  ADD COLUMN recovery_idempotency_key TEXT NULL,
  ADD CONSTRAINT ordinary_reply_recovery_identity_check CHECK (
    (operation_kind='PRIMARY' AND causal_operation_id IS NULL
      AND recovery_attention_occurrence_id IS NULL
      AND recovery_resolution_plan_id IS NULL
      AND recovery_idempotency_key IS NULL)
    OR
    (operation_kind='HISTORICAL_CORRECTIVE' AND causal_operation_id IS NOT NULL
      AND BTRIM(COALESCE(recovery_attention_occurrence_id,''))<>''
      AND recovery_resolution_plan_id IS NOT NULL
      AND BTRIM(COALESCE(recovery_idempotency_key,''))<>'')
  );

ALTER TABLE public.ordinary_chat_reply_operations
  DROP CONSTRAINT ordinary_chat_reply_operation_telegram_account_scope_telegr_key;

CREATE UNIQUE INDEX uq_ordinary_reply_primary_inbound
  ON public.ordinary_chat_reply_operations(
    telegram_account_scope,telegram_chat_id,inbound_telegram_message_id
  ) WHERE operation_kind='PRIMARY';

CREATE UNIQUE INDEX uq_ordinary_reply_recovery_idempotency
  ON public.ordinary_chat_reply_operations(recovery_idempotency_key)
  WHERE recovery_idempotency_key IS NOT NULL;

CREATE INDEX ix_ordinary_reply_recovery_cause
  ON public.ordinary_chat_reply_operations(causal_operation_id,created_at)
  WHERE operation_kind='HISTORICAL_CORRECTIVE';

COMMIT;
