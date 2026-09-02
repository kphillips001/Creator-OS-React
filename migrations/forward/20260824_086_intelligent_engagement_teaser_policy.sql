BEGIN;

ALTER TABLE public.telegram_engagement_teaser_delivery_operations
    ADD COLUMN IF NOT EXISTS engagement_strategy TEXT NULL,
    ADD COLUMN IF NOT EXISTS decision_reason_code TEXT NULL,
    ADD COLUMN IF NOT EXISTS decision_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS policy_version TEXT NULL,
    ADD COLUMN IF NOT EXISTS next_inbound_message_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS next_inbound_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS response_latency_seconds BIGINT NULL,
    ADD COLUMN IF NOT EXISTS response_attribution TEXT NULL;

ALTER TABLE public.telegram_engagement_teaser_delivery_operations
    DROP CONSTRAINT IF EXISTS telegram_engagement_teaser_strategy_check;
ALTER TABLE public.telegram_engagement_teaser_delivery_operations
    ADD CONSTRAINT telegram_engagement_teaser_strategy_check CHECK (
        engagement_strategy IS NULL OR engagement_strategy IN ('WARM_UP','RE_ENGAGE','RELATIONSHIP')
    );

CREATE TABLE IF NOT EXISTS public.engagement_teaser_policy_decisions (
    decision_id UUID PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('ACTIVE_INBOUND','SCHEDULED_REENGAGEMENT')),
    decision TEXT NOT NULL CHECK (decision IN ('SEND_FREE_ENGAGEMENT_TEASER','SEND_NONE')),
    engagement_strategy TEXT NULL CHECK (
        engagement_strategy IS NULL OR engagement_strategy IN ('WARM_UP','RE_ENGAGE','RELATIONSHIP')
    ),
    reason_code TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    suppression_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL,
    selected_asset_id BIGINT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    operation_id UUID NULL REFERENCES public.telegram_engagement_teaser_delivery_operations(operation_id) ON DELETE RESTRICT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id, fanvue_account_id, correlation_id)
);

CREATE INDEX IF NOT EXISTS idx_engagement_teaser_policy_customer
    ON public.engagement_teaser_policy_decisions (
        creator_profile_id,fanvue_account_id,fanvue_user_id,decided_at DESC
    );

ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_instruction_type_check;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_instruction_type_check CHECK (
        instruction_type IN ('CONVERSATION_RULE','SALES_RULE','SAFETY_RULE',
          'SAFETY_HARD_STOP','HARD_STOP','KNOWLEDGE','ENGAGEMENT_RULE')
    );
ALTER TABLE public.ai_runtime_instructions
    ADD COLUMN IF NOT EXISTS policy_configuration JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.ai_runtime_instruction_revisions
    ADD COLUMN IF NOT EXISTS policy_configuration JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
