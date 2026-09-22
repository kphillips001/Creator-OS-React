BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.ordinary_chat_reply_operations
     WHERE operation_kind='HISTORICAL_CORRECTIVE'
       AND recovery_parent_operation_id IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Rollback blocked: follow-up historical corrective lineage exists.';
  END IF;
END $$;

DROP INDEX IF EXISTS public.ix_ordinary_reply_recovery_parent;

ALTER TABLE public.ordinary_chat_reply_operations
  DROP COLUMN recovery_parent_operation_id;

COMMIT;
