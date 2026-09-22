-- Never remove live invocation/acceptance evidence during rollback.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.telegram_operator_message_operations
               WHERE transport_evidence <> '{}'::jsonb) THEN
        RAISE EXCEPTION 'Transport evidence exists; rollback requires retaining delivery evidence';
    END IF;
END $$;
DROP INDEX IF EXISTS public.telegram_operator_invocation_recovery_idx;
ALTER TABLE public.telegram_operator_message_operations
    DROP CONSTRAINT IF EXISTS telegram_operator_transport_evidence_object,
    DROP COLUMN IF EXISTS transport_evidence;
