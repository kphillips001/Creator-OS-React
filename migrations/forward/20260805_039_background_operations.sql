BEGIN;

CREATE TABLE public.background_operations (
  operation_id UUID PRIMARY KEY,
  operation_type TEXT NOT NULL,
  originating_workspace TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
  account_id BIGINT REFERENCES public.fanvue_accounts(id) ON DELETE SET NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  executor_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED'
    CHECK (status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','SUCCEEDED','PARTIAL','FAILED','CANCEL_REQUESTED','CANCELLED')),
  progress_current INTEGER NOT NULL DEFAULT 0 CHECK (progress_current >= 0),
  progress_total INTEGER NOT NULL DEFAULT 0 CHECK (progress_total >= 0),
  progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
  current_stage TEXT,
  stage_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  result_location TEXT,
  result_reference TEXT,
  error_code TEXT,
  error_message TEXT,
  cancellation_supported BOOLEAN NOT NULL DEFAULT FALSE,
  cancellation_requested_at TIMESTAMPTZ,
  worker_id TEXT,
  lease_expires_at TIMESTAMPTZ,
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  operation_version TEXT NOT NULL DEFAULT 'background_operation_v1',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.background_operation_events (
  event_id BIGSERIAL PRIMARY KEY,
  operation_id UUID NOT NULL REFERENCES public.background_operations(operation_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  previous_status TEXT,
  new_status TEXT,
  stage TEXT,
  message TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_background_operations_active_idempotency
  ON public.background_operations (creator_profile_id, idempotency_key)
  WHERE status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED');
CREATE INDEX idx_background_operations_creator_account
  ON public.background_operations (creator_profile_id, account_id, created_at DESC);
CREATE INDEX idx_background_operations_active
  ON public.background_operations (creator_profile_id, status, updated_at DESC)
  WHERE status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED');
CREATE INDEX idx_background_operations_workspace_subject
  ON public.background_operations (creator_profile_id, originating_workspace, subject_type, subject_id, created_at DESC);
CREATE INDEX idx_background_operations_status_lease
  ON public.background_operations (status, lease_expires_at, created_at);
CREATE INDEX idx_background_operation_events_operation
  ON public.background_operation_events (operation_id, event_id);

COMMIT;
