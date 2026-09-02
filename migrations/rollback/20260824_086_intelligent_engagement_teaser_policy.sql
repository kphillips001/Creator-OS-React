BEGIN;
DROP TABLE IF EXISTS public.engagement_teaser_policy_decisions;
ALTER TABLE public.telegram_engagement_teaser_delivery_operations
    DROP COLUMN IF EXISTS response_attribution,
    DROP COLUMN IF EXISTS response_latency_seconds,
    DROP COLUMN IF EXISTS next_inbound_at,
    DROP COLUMN IF EXISTS next_inbound_message_id,
    DROP COLUMN IF EXISTS policy_version,
    DROP COLUMN IF EXISTS decision_evidence,
    DROP COLUMN IF EXISTS decision_reason_code,
    DROP COLUMN IF EXISTS engagement_strategy;
ALTER TABLE public.ai_runtime_instruction_revisions DROP COLUMN IF EXISTS policy_configuration;
ALTER TABLE public.ai_runtime_instructions DROP COLUMN IF EXISTS policy_configuration;
COMMIT;
