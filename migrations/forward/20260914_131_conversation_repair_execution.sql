BEGIN;
CREATE TABLE public.conversation_repair_executions(
 execution_id UUID PRIMARY KEY,authorization_id UUID NOT NULL UNIQUE REFERENCES public.conversation_repair_execution_authorizations(authorization_id) ON DELETE RESTRICT,
 proposal_id UUID NOT NULL REFERENCES public.conversation_repair_proposals(proposal_id) ON DELETE RESTRICT,
 creator_profile_id BIGINT NOT NULL,fanvue_account_id BIGINT NOT NULL,
 state TEXT NOT NULL CHECK(state IN('AUTHORIZED','EXECUTING','TESTING','PASSED','FAILED','ROLLED_BACK','DEPLOYED','STALE','EXPIRED')),
 workflow TEXT NOT NULL,executor_identity TEXT NOT NULL,developer_task_id UUID NULL,developer_execution_id UUID NULL,
 files_changed JSONB NOT NULL DEFAULT '[]',tests_result JSONB NOT NULL DEFAULT '{}',rollback_evidence JSONB NOT NULL DEFAULT '{}',deployment_evidence JSONB NOT NULL DEFAULT '{}',
 started_at TIMESTAMPTZ NULL,completed_at TIMESTAMPTZ NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE public.conversation_repair_execution_events(
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),execution_id UUID NOT NULL REFERENCES public.conversation_repair_executions(execution_id) ON DELETE RESTRICT,
 event_type TEXT NOT NULL CHECK(event_type IN('EXECUTION_STARTED','TESTING_STARTED','TESTS_PASSED','TESTS_FAILED','ROLLBACK_STARTED','ROLLBACK_COMPLETED','DEPLOYED','EXECUTION_FAILED')),
 event_data JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
COMMIT;
