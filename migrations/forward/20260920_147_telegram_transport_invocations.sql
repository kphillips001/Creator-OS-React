-- Additive only: historical operations retain an empty evidence object.
ALTER TABLE public.telegram_operator_message_operations
    ADD COLUMN IF NOT EXISTS transport_evidence jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.telegram_operator_message_operations
    ADD CONSTRAINT telegram_operator_transport_evidence_object
    CHECK (jsonb_typeof(transport_evidence) = 'object');
CREATE INDEX IF NOT EXISTS telegram_operator_invocation_recovery_idx
    ON public.telegram_operator_message_operations (state)
    WHERE state = 'SENDING' AND transport_evidence ? 'invocation_owner';
