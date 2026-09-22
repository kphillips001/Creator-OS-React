BEGIN;

ALTER TABLE public.ordinary_chat_reply_operations
  ADD COLUMN recovery_parent_operation_id UUID NULL
    REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE RESTRICT;

-- Existing corrective rows are immutable historical evidence.  In particular,
-- do not backfill this column: NULL means "created before immediate-parent
-- lineage existed".  The repository requires a parent on every new corrective.

CREATE INDEX ix_ordinary_reply_recovery_parent
  ON public.ordinary_chat_reply_operations(recovery_parent_operation_id,created_at)
  WHERE operation_kind='HISTORICAL_CORRECTIVE';

COMMIT;
