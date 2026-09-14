BEGIN;
ALTER TABLE public.conversation_repair_execution_authorizations ADD COLUMN baseline_sha TEXT NULL CHECK(baseline_sha IS NULL OR length(baseline_sha)=40);
ALTER TABLE public.conversation_repair_executions DROP CONSTRAINT conversation_repair_executions_state_check,
 ADD CONSTRAINT conversation_repair_executions_state_check CHECK(state IN('AUTHORIZED','EXECUTING','TESTING','FAILED','STALE','EXPIRED','READY_FOR_DEPLOYMENT')),
 ADD COLUMN baseline_sha TEXT NULL CHECK(baseline_sha IS NULL OR length(baseline_sha)=40),ADD COLUMN staging_branch TEXT NULL,ADD COLUMN staging_worktree_identity TEXT NULL,ADD COLUMN staging_worktree_path TEXT NULL,ADD COLUMN staged_diff_digest TEXT NULL,ADD COLUMN failure_reason TEXT NULL,ADD COLUMN ready_for_deployment_at TIMESTAMPTZ NULL;
ALTER TABLE public.conversation_repair_execution_events DROP CONSTRAINT conversation_repair_execution_events_event_type_check,
 ADD CONSTRAINT conversation_repair_execution_events_event_type_check CHECK(event_type IN('EXECUTION_STARTED','STAGING_CREATED','AGENT_STARTED','AGENT_COMPLETED','TESTING_STARTED','TESTS_PASSED','TESTS_FAILED','OUT_OF_SCOPE_EDIT','READY_FOR_DEPLOYMENT','STALE','EXPIRED','FAILED','STAGING_DISCARDED'));
COMMIT;
