BEGIN;
UPDATE public.conversation_repair_executions SET state='PASSED' WHERE state='READY_FOR_DEPLOYMENT';
ALTER TABLE public.conversation_repair_execution_events DROP CONSTRAINT conversation_repair_execution_events_event_type_check,ADD CONSTRAINT conversation_repair_execution_events_event_type_check CHECK(event_type IN('EXECUTION_STARTED','TESTING_STARTED','TESTS_PASSED','TESTS_FAILED','ROLLBACK_STARTED','ROLLBACK_COMPLETED','DEPLOYED','EXECUTION_FAILED'));
ALTER TABLE public.conversation_repair_executions DROP CONSTRAINT conversation_repair_executions_state_check,ADD CONSTRAINT conversation_repair_executions_state_check CHECK(state IN('AUTHORIZED','EXECUTING','TESTING','PASSED','FAILED','ROLLED_BACK','DEPLOYED','STALE','EXPIRED')),DROP COLUMN ready_for_deployment_at,DROP COLUMN failure_reason,DROP COLUMN staged_diff_digest,DROP COLUMN staging_worktree_path,DROP COLUMN staging_worktree_identity,DROP COLUMN staging_branch,DROP COLUMN baseline_sha;
ALTER TABLE public.conversation_repair_execution_authorizations DROP COLUMN baseline_sha;
COMMIT;
