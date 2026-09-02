BEGIN;
ALTER TABLE public.ai_runtime_instructions
    DROP CONSTRAINT IF EXISTS ai_runtime_instructions_policy_shape;
ALTER TABLE public.ai_runtime_instructions
    ADD CONSTRAINT ai_runtime_instructions_policy_shape CHECK (
        (instruction_type='SAFETY_HARD_STOP'
          AND policy_key='UNDERAGE_CUSTOMER' AND enforcement_mode='BACKEND')
        OR (instruction_type<>'SAFETY_HARD_STOP' AND policy_key IS NULL)
    );
COMMIT;
