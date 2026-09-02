BEGIN;

CREATE TABLE IF NOT EXISTS public.sales_readiness_decisions (
    decision_id UUID PRIMARY KEY,
    correlation_id TEXT NOT NULL CHECK (BTRIM(correlation_id)<>''),
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NOT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    warmup_depth INTEGER NOT NULL CHECK (warmup_depth>=0),
    customer_segment TEXT NOT NULL CHECK (customer_segment IN (
      'PROSPECT','RETURNING_NON_BUYER','FIRST_TIME_BUYER','REPEAT_BUYER',
      'ACTIVE_SESSION','RECENT_PURCHASER','RECENT_DECLINE')),
    benchmark_position TEXT NOT NULL CHECK (benchmark_position IN (
      'BELOW_BENCHMARK','NORMAL_BENCHMARK','BEYOND_BENCHMARK')),
    direct_intent BOOLEAN NOT NULL,
    strong_readiness BOOLEAN NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
      'CONTINUE_CONVERSATION','AUTHORIZE_COMMERCIAL_PROGRESSION')),
    reason_code TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    suppression_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL,
    selected_offering_id UUID NULL REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    selected_publication_id UUID NULL REFERENCES public.commercial_publications(publication_id) ON DELETE RESTRICT,
    resulting_sales_action TEXT NULL CHECK (resulting_sales_action IS NULL OR resulting_sales_action IN (
      'CONTINUE_CONVERSATION','TEASE','BUILD_INTEREST','PRESENT_OFFER','BACK_OFF','NO_SALE')),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id,fanvue_account_id,correlation_id)
);

CREATE INDEX IF NOT EXISTS idx_sales_readiness_customer_timing
  ON public.sales_readiness_decisions (
    creator_profile_id,fanvue_account_id,fanvue_user_id,decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_sales_readiness_learning
  ON public.sales_readiness_decisions (
    creator_profile_id,customer_segment,resulting_sales_action,warmup_depth,decided_at DESC);

ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_policy_shape;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_policy_shape CHECK (
        (instruction_type='SAFETY_HARD_STOP'
          AND policy_key='UNDERAGE_CUSTOMER' AND enforcement_mode='BACKEND')
        OR
        (instruction_type='ENGAGEMENT_RULE'
          AND policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS'
          AND enforcement_mode='BACKEND')
        OR
        (instruction_type='SALES_RULE'
          AND policy_key='ADAPTIVE_SALES_READINESS'
          AND enforcement_mode='BACKEND')
        OR
        (instruction_type NOT IN ('SAFETY_HARD_STOP','ENGAGEMENT_RULE','SALES_RULE')
          AND policy_key IS NULL)
    );

COMMIT;
