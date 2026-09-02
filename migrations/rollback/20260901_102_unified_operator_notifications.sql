BEGIN;

DELETE FROM public.operator_notification_operations
WHERE notification_type = 'AVA_CONVERSATION_REVIEW'
   OR abuse_incident_id IS NULL;
UPDATE public.operator_notification_operations
SET notification_type = 'CUSTOMER_ABUSE_REVIEW'
WHERE notification_type = 'ABUSIVE_CUSTOMER_REVIEW';
DROP INDEX IF EXISTS public.operator_notification_customer_review_idx;
ALTER TABLE public.operator_notification_operations
    DROP COLUMN reviewed_at,
    DROP COLUMN incident_window_started_at,
    DROP COLUMN severity,
    DROP COLUMN quality_reason,
    DROP COLUMN source_correlation_id,
    DROP COLUMN telegram_chat_id,
    DROP COLUMN telegram_user_id,
    DROP COLUMN fanvue_account_id,
    DROP COLUMN creator_profile_id;
ALTER TABLE public.operator_notification_operations
    ALTER COLUMN abuse_incident_id SET NOT NULL;
ALTER TABLE public.operator_notification_operations
    DROP CONSTRAINT operator_notification_operations_notification_type_check;
ALTER TABLE public.operator_notification_operations
    ADD CONSTRAINT operator_notification_operations_notification_type_check
    CHECK (notification_type IN ('CUSTOMER_ABUSE_REVIEW'));

COMMIT;
