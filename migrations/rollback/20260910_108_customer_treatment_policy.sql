BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.ai_runtime_instructions
               WHERE instruction_type='CUSTOMER_TREATMENT_POLICY') THEN
        RAISE EXCEPTION 'Disable/remove CUSTOMER_TREATMENT_POLICY records through an approved data-retention procedure before rollback.';
    END IF;
END $$;

DROP INDEX IF EXISTS public.uq_ai_runtime_customer_treatment;
ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_policy_shape;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_policy_shape CHECK (
        (instruction_type='SAFETY_HARD_STOP' AND policy_key='UNDERAGE_CUSTOMER' AND enforcement_mode='BACKEND')
        OR (instruction_type='ENGAGEMENT_RULE' AND policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS' AND enforcement_mode='BACKEND')
        OR (instruction_type='SALES_RULE' AND policy_key='ADAPTIVE_SALES_READINESS' AND enforcement_mode='BACKEND')
        OR (instruction_type NOT IN ('SAFETY_HARD_STOP','ENGAGEMENT_RULE','SALES_RULE') AND policy_key IS NULL)
    );
ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_instruction_type_check;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_instruction_type_check CHECK (
        instruction_type IN ('CONVERSATION_RULE','SALES_RULE','SAFETY_RULE',
        'SAFETY_HARD_STOP','HARD_STOP','KNOWLEDGE','ENGAGEMENT_RULE')
    );

COMMIT;
