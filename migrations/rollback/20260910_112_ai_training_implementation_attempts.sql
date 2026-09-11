BEGIN;

DROP TABLE IF EXISTS public.ai_training_implementation_attempts;
ALTER TABLE public.developer_agent_executions
    DROP CONSTRAINT IF EXISTS developer_agent_executions_execution_task_key;

COMMIT;
