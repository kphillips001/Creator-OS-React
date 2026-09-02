ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_instruction_type_check;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_instruction_type_check CHECK (
        instruction_type IN ('CONVERSATION_RULE','SALES_RULE','SAFETY_RULE',
        'SAFETY_HARD_STOP','HARD_STOP','KNOWLEDGE')
    );
ALTER TABLE public.ai_runtime_instruction_revisions
    ADD COLUMN IF NOT EXISTS policy_key TEXT NULL,
    ADD COLUMN IF NOT EXISTS enforcement_mode TEXT NOT NULL DEFAULT 'PROMPT';
ALTER TABLE public.ai_runtime_instructions
    ADD COLUMN IF NOT EXISTS policy_key TEXT NULL,
    ADD COLUMN IF NOT EXISTS enforcement_mode TEXT NOT NULL DEFAULT 'PROMPT'
        CHECK (enforcement_mode IN ('PROMPT','BACKEND'));
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_policy_shape CHECK (
        (instruction_type='SAFETY_HARD_STOP' AND policy_key='UNDERAGE_CUSTOMER'
            AND enforcement_mode='BACKEND')
        OR (instruction_type<>'SAFETY_HARD_STOP' AND policy_key IS NULL)
    );

CREATE TABLE public.customer_interaction_safety_states (
    safety_state_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    safety_status TEXT NOT NULL CHECK (safety_status IN ('NORMAL','UNDERAGE_BLOCKED')),
    reason TEXT NOT NULL CHECK (BTRIM(reason)<>''),
    source TEXT NOT NULL CHECK (source IN ('OPERATOR')),
    effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id,fanvue_account_id,fanvue_user_id)
);

CREATE TABLE public.customer_interaction_safety_history (
    history_id UUID PRIMARY KEY,
    safety_state_id UUID NOT NULL REFERENCES public.customer_interaction_safety_states(safety_state_id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    fanvue_user_id BIGINT NOT NULL,
    previous_status TEXT NULL,
    new_status TEXT NOT NULL CHECK (new_status IN ('NORMAL','UNDERAGE_BLOCKED')),
    reason TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('OPERATOR')),
    actor_identifier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_customer_interaction_safety_lookup
    ON public.customer_interaction_safety_states(fanvue_account_id,fanvue_user_id,creator_profile_id);
CREATE INDEX idx_customer_interaction_safety_history
    ON public.customer_interaction_safety_history(safety_state_id,created_at DESC);
