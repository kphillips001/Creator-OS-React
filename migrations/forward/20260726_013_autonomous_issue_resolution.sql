CREATE TABLE IF NOT EXISTS public.autonomous_issue_resolutions (
    resolution_id UUID PRIMARY KEY,
    issue_identifier TEXT NOT NULL,
    issue_snapshot JSONB NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
        'AUTO_FIX','USER_ACTION_REQUIRED','CONFIGURATION_REQUIRED',
        'NOT_FIXABLE','ALREADY_RESOLVED'
    )),
    decision_reason TEXT NOT NULL,
    required_action TEXT,
    destination_path TEXT,
    developer_agent_task_id UUID REFERENCES public.developer_agent_tasks(task_id),
    developer_agent_execution_id UUID REFERENCES public.developer_agent_executions(execution_id),
    validation_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (validation_status IN (
        'PENDING','RUNNING','PASSED','FAILED','NOT_REQUIRED'
    )),
    validation_evidence JSONB NOT NULL DEFAULT '{}'::JSONB,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'IN_PROGRESS','RESOLVED','PARTIALLY_RESOLVED','COULD_NOT_RESOLVE',
        'USER_ACTION_REQUIRED','ALREADY_RESOLVED'
    )),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS autonomous_issue_resolutions_created_idx
    ON public.autonomous_issue_resolutions(created_at DESC);
CREATE INDEX IF NOT EXISTS autonomous_issue_resolutions_execution_idx
    ON public.autonomous_issue_resolutions(developer_agent_execution_id);
