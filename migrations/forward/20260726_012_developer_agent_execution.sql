CREATE TABLE IF NOT EXISTS public.developer_agent_tasks (
    task_id UUID PRIMARY KEY,
    issue_identifier TEXT NOT NULL,
    investigation_package TEXT NOT NULL,
    implementation_task TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    expected_branch TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'DRAFT','AWAITING_APPROVAL','APPROVED','REJECTED'
    )),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.developer_agent_executions (
    execution_id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES public.developer_agent_tasks(task_id),
    status TEXT NOT NULL CHECK (status IN (
        'QUEUED','STARTING','RUNNING','WAITING_FOR_INPUT','TESTING',
        'COMPLETED','FAILED','CANCELLED','INTERRUPTED'
    )),
    codex_session_id TEXT,
    initial_git_status TEXT,
    initial_branch TEXT,
    initial_head TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    cancellation_reason TEXT,
    final_report JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.developer_agent_events (
    event_id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES public.developer_agent_executions(execution_id),
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS developer_agent_events_execution_idx
    ON public.developer_agent_events(execution_id, event_id);

CREATE TABLE IF NOT EXISTS public.developer_agent_notifications (
    notification_id UUID PRIMARY KEY,
    task_id UUID REFERENCES public.developer_agent_tasks(task_id),
    execution_id UUID REFERENCES public.developer_agent_executions(execution_id),
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS developer_agent_notifications_created_idx
    ON public.developer_agent_notifications(created_at DESC);

CREATE TABLE IF NOT EXISTS public.developer_agent_reviews (
    review_id UUID PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES public.developer_agent_executions(execution_id),
    status TEXT NOT NULL CHECK (status IN (
        'PENDING','ACKNOWLEDGED','REJECTED','ARCHIVED'
    )),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
