CREATE TABLE IF NOT EXISTS public.ai_runtime_instructions (
    instruction_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    scope TEXT NOT NULL CHECK (scope IN ('GLOBAL','CUSTOMER')),
    customer_fanvue_user_id BIGINT NULL
        REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    instruction_type TEXT NOT NULL CHECK (instruction_type IN (
        'CONVERSATION_RULE','SALES_RULE','SAFETY_RULE','HARD_STOP','KNOWLEDGE'
    )),
    original_operator_text TEXT NOT NULL CHECK (BTRIM(original_operator_text) <> ''),
    normalized_instruction TEXT NOT NULL CHECK (BTRIM(normalized_instruction) <> ''),
    status TEXT NOT NULL CHECK (status IN (
        'DRAFT','ENABLED','DISABLED','ARCHIVED','REQUIRES_IMPLEMENTATION'
    )),
    priority INTEGER NOT NULL DEFAULT 100 CHECK (priority BETWEEN 0 AND 1000),
    source TEXT NOT NULL DEFAULT 'OPERATOR' CHECK (source IN ('OPERATOR')),
    classification_reason TEXT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enabled_at TIMESTAMPTZ NULL,
    disabled_at TIMESTAMPTZ NULL,
    archived_at TIMESTAMPTZ NULL,
    CHECK (
        (scope='GLOBAL' AND customer_fanvue_user_id IS NULL)
        OR (scope='CUSTOMER' AND customer_fanvue_user_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_runtime_instructions_active_global
    ON public.ai_runtime_instructions (
        fanvue_account_id,creator_profile_id,priority,instruction_id
    ) WHERE scope='GLOBAL' AND instruction_type='CONVERSATION_RULE'
        AND status='ENABLED';

CREATE TABLE IF NOT EXISTS public.ai_runtime_instruction_revisions (
    revision_id UUID PRIMARY KEY,
    instruction_id UUID NOT NULL
        REFERENCES public.ai_runtime_instructions(instruction_id) ON DELETE RESTRICT,
    version INTEGER NOT NULL CHECK (version > 0),
    action TEXT NOT NULL CHECK (action IN (
        'CREATED','EDITED','ENABLED','DISABLED','ARCHIVED'
    )),
    original_operator_text TEXT NOT NULL,
    normalized_instruction TEXT NOT NULL,
    instruction_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    source TEXT NOT NULL,
    classification_reason TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (instruction_id,version)
);

CREATE INDEX IF NOT EXISTS idx_ai_runtime_instruction_revisions_history
    ON public.ai_runtime_instruction_revisions (instruction_id,version DESC);
