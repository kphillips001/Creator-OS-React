BEGIN;

CREATE TABLE IF NOT EXISTS public.ai_training_history_baselines (
    baseline_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    baseline_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (creator_profile_id, fanvue_account_id)
);

CREATE TABLE IF NOT EXISTS public.ai_training_history_baseline_retained_instructions (
    baseline_id UUID NOT NULL REFERENCES public.ai_training_history_baselines(baseline_id) ON DELETE CASCADE,
    instruction_id UUID NOT NULL REFERENCES public.ai_runtime_instructions(instruction_id) ON DELETE RESTRICT,
    PRIMARY KEY (baseline_id, instruction_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_training_history_baseline_account
    ON public.ai_training_history_baselines(creator_profile_id, fanvue_account_id, baseline_at);

COMMIT;
