DROP TABLE IF EXISTS public.customer_interaction_safety_history;
DROP TABLE IF EXISTS public.customer_interaction_safety_states;
ALTER TABLE public.ai_runtime_instructions DROP CONSTRAINT IF EXISTS ai_runtime_instructions_policy_shape;
ALTER TABLE public.ai_runtime_instruction_revisions DROP COLUMN IF EXISTS enforcement_mode;
ALTER TABLE public.ai_runtime_instruction_revisions DROP COLUMN IF EXISTS policy_key;
ALTER TABLE public.ai_runtime_instructions DROP COLUMN IF EXISTS enforcement_mode;
ALTER TABLE public.ai_runtime_instructions DROP COLUMN IF EXISTS policy_key;
ALTER TABLE public.ai_runtime_instructions DROP CONSTRAINT IF EXISTS ai_runtime_instructions_instruction_type_check;
ALTER TABLE public.ai_runtime_instructions ADD CONSTRAINT ai_runtime_instructions_instruction_type_check CHECK (
    instruction_type IN ('CONVERSATION_RULE','SALES_RULE','SAFETY_RULE','HARD_STOP','KNOWLEDGE')
);
