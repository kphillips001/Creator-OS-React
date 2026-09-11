BEGIN;

ALTER TABLE public.developer_agent_executions
    ADD CONSTRAINT developer_agent_executions_execution_task_key
    UNIQUE (execution_id, task_id);

CREATE TABLE public.ai_training_implementation_attempts (
    attempt_id UUID PRIMARY KEY,
    work_item_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    implementation_brief_version INTEGER NOT NULL CHECK (implementation_brief_version > 0),
    developer_agent_task_id UUID NOT NULL,
    developer_agent_execution_id UUID NULL,
    status TEXT NOT NULL CHECK (status IN (
        'READY_FOR_IMPLEMENTATION','IMPLEMENTING','NEEDS_VERIFICATION',
        'FAILED','VERIFIED','SUPERSEDED'
    )),
    approved_at TIMESTAMPTZ NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ai_training_implementation_attempts_work_number_key UNIQUE (work_item_id, attempt_number),
    CONSTRAINT ai_training_implementation_attempts_task_key UNIQUE (developer_agent_task_id),
    CONSTRAINT ai_training_implementation_attempts_execution_key UNIQUE (developer_agent_execution_id),
    CONSTRAINT ai_training_attempts_work_item_fkey
        FOREIGN KEY (work_item_id) REFERENCES public.ai_training_work_items(work_item_id) ON DELETE CASCADE,
    CONSTRAINT ai_training_attempts_task_fkey
        FOREIGN KEY (developer_agent_task_id) REFERENCES public.developer_agent_tasks(task_id),
    CONSTRAINT ai_training_implementation_attempts_execution_task_fkey
        FOREIGN KEY (developer_agent_execution_id, developer_agent_task_id)
        REFERENCES public.developer_agent_executions(execution_id, task_id)
);

CREATE INDEX ai_training_implementation_attempts_work_created_idx
    ON public.ai_training_implementation_attempts(work_item_id, attempt_number DESC);

COMMIT;
