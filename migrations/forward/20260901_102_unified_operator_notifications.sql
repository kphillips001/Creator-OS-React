BEGIN;

ALTER TABLE public.operator_notification_operations
    DROP CONSTRAINT operator_notification_operations_notification_type_check;
ALTER TABLE public.operator_notification_operations
    ADD CONSTRAINT operator_notification_operations_notification_type_check
    CHECK (notification_type IN (
        'CUSTOMER_ABUSE_REVIEW',
        'ABUSIVE_CUSTOMER_REVIEW',
        'AVA_CONVERSATION_REVIEW'
    ));
ALTER TABLE public.operator_notification_operations
    ALTER COLUMN abuse_incident_id DROP NOT NULL;
ALTER TABLE public.operator_notification_operations
    ADD COLUMN creator_profile_id BIGINT NULL,
    ADD COLUMN fanvue_account_id BIGINT NULL,
    ADD COLUMN telegram_user_id BIGINT NULL,
    ADD COLUMN telegram_chat_id BIGINT NULL,
    ADD COLUMN source_correlation_id TEXT NULL,
    ADD COLUMN quality_reason TEXT NULL,
    ADD COLUMN severity TEXT NULL CHECK (severity IN ('INFO','REVIEW','HIGH')),
    ADD COLUMN incident_window_started_at TIMESTAMPTZ NULL,
    ADD COLUMN reviewed_at TIMESTAMPTZ NULL;

CREATE INDEX operator_notification_customer_review_idx
    ON public.operator_notification_operations
       (notification_type,telegram_user_id,quality_reason,incident_window_started_at DESC);

COMMIT;
