BEGIN;

ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_instruction_type_check;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_instruction_type_check CHECK (
        instruction_type IN ('CONVERSATION_RULE','SALES_RULE','SAFETY_RULE',
        'SAFETY_HARD_STOP','HARD_STOP','KNOWLEDGE','ENGAGEMENT_RULE',
        'CUSTOMER_TREATMENT_POLICY')
    );

ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_policy_shape;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_policy_shape CHECK (
        (instruction_type='SAFETY_HARD_STOP'
          AND policy_key='UNDERAGE_CUSTOMER' AND enforcement_mode='BACKEND')
        OR (instruction_type='ENGAGEMENT_RULE'
          AND policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS' AND enforcement_mode='BACKEND')
        OR (instruction_type='SALES_RULE'
          AND policy_key='ADAPTIVE_SALES_READINESS' AND enforcement_mode='BACKEND')
        OR (instruction_type='CUSTOMER_TREATMENT_POLICY'
          AND scope='CUSTOMER' AND customer_fanvue_user_id IS NOT NULL
          AND policy_key='CUSTOMER_TREATMENT_POLICY' AND enforcement_mode='BACKEND')
        OR (instruction_type NOT IN ('SAFETY_HARD_STOP','ENGAGEMENT_RULE','SALES_RULE',
          'CUSTOMER_TREATMENT_POLICY') AND policy_key IS NULL)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_runtime_customer_treatment
    ON public.ai_runtime_instructions (
        creator_profile_id,fanvue_account_id,customer_fanvue_user_id,policy_key
    ) WHERE scope='CUSTOMER' AND instruction_type='CUSTOMER_TREATMENT_POLICY';

COMMIT;
