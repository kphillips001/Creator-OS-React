BEGIN;

CREATE TABLE IF NOT EXISTS public.ai_training_work_items (
    work_item_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('GLOBAL','CUSTOMER')),
    customer_fanvue_user_id BIGINT,
    original_request_text TEXT NOT NULL CHECK (BTRIM(original_request_text) <> ''),
    status TEXT NOT NULL CHECK (status IN ('TODO','READY_TO_APPLY','REQUIRES_IMPLEMENTATION','IMPLEMENTED','REJECTED','CLOSED','SUPERSEDED')),
    classification TEXT,
    classification_rationale TEXT,
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    linked_instruction_id UUID REFERENCES public.ai_runtime_instructions(instruction_id) ON DELETE SET NULL,
    linked_future_task_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT ai_training_work_item_customer_scope CHECK (
        (scope='GLOBAL' AND customer_fanvue_user_id IS NULL)
        OR (scope='CUSTOMER' AND customer_fanvue_user_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_training_work_items_account_status
    ON public.ai_training_work_items(creator_profile_id,fanvue_account_id,status,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_training_work_items_customer
    ON public.ai_training_work_items(creator_profile_id,fanvue_account_id,customer_fanvue_user_id,updated_at DESC)
    WHERE scope='CUSTOMER';

COMMIT;
