BEGIN;

CREATE TABLE public.conversation_attention_inspections (
    inspection_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    relationship_key TEXT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    attention_occurrence_id TEXT NOT NULL,
    evidence_digest TEXT NOT NULL CHECK (length(evidence_digest)=64),
    state_fingerprint TEXT NOT NULL CHECK (length(state_fingerprint)=64),
    failure_signature TEXT NOT NULL,
    root_cause_scope TEXT NOT NULL CHECK (root_cause_scope IN
      ('CUSTOMER_ONLY','MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM','OBSOLETE','AMBIGUOUS')),
    validated_result JSONB NOT NULL,
    evidence_references JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE public.conversation_resolution_plans (
    plan_id UUID PRIMARY KEY,
    inspection_id UUID NOT NULL REFERENCES public.conversation_attention_inspections(inspection_id),
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    relationship_key TEXT NOT NULL,
    telegram_user_id BIGINT NOT NULL,
    attention_occurrence_id TEXT NOT NULL,
    state_fingerprint TEXT NOT NULL CHECK (length(state_fingerprint)=64),
    root_cause_scope TEXT NOT NULL,
    target_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id),
    causal_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id),
    action_type TEXT NOT NULL CHECK (action_type IN
      ('ACKNOWLEDGE_ONLY','REQUEUE_CORRECTIVE_REPLY','RESOLVE_AS_SUPERSEDED')),
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,
    expected_mutation_entities JSONB NOT NULL DEFAULT '[]'::JSONB,
    provider_generation_possible BOOLEAN NOT NULL,
    customer_visible_send_possible BOOLEAN NOT NULL,
    code_change_required BOOLEAN NOT NULL DEFAULT FALSE,
    schema_change_required BOOLEAN NOT NULL DEFAULT FALSE,
    config_change_required BOOLEAN NOT NULL DEFAULT FALSE,
    runtime_restart_required BOOLEAN NOT NULL DEFAULT FALSE,
    global_impact_possible BOOLEAN NOT NULL DEFAULT FALSE,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    signature TEXT NOT NULL,
    approval_state TEXT NOT NULL DEFAULT 'PENDING' CHECK
      (approval_state IN ('PENDING','APPROVED','REJECTED','CANCELLED','EXPIRED')),
    approved_by TEXT NULL,
    approved_at TIMESTAMPTZ NULL,
    execution_state TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK
      (execution_state IN ('NOT_STARTED','EXECUTING','SUCCEEDED','FAILED','STALE_REJECTED')),
    idempotency_key TEXT NOT NULL UNIQUE,
    execution_result JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (inspection_id, action_type)
);

CREATE TABLE public.conversation_resolution_executions (
    execution_id UUID PRIMARY KEY,
    plan_id UUID NOT NULL UNIQUE REFERENCES public.conversation_resolution_plans(plan_id),
    action_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('EXECUTING','SUCCEEDED','FAILED','STALE_REJECTED')),
    canonical_service TEXT NOT NULL,
    records_changed JSONB NOT NULL DEFAULT '[]'::JSONB,
    provider_operation_id TEXT NULL,
    telegram_delivery_operation_id TEXT NULL,
    result JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE public.conversation_resolution_events (
    event_id BIGSERIAL PRIMARY KEY,
    inspection_id UUID NULL REFERENCES public.conversation_attention_inspections(inspection_id),
    plan_id UUID NULL REFERENCES public.conversation_resolution_plans(plan_id),
    execution_id UUID NULL REFERENCES public.conversation_resolution_executions(execution_id),
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_attention_inspection_scope ON public.conversation_attention_inspections
  (creator_profile_id,fanvue_account_id,telegram_user_id,created_at DESC);
CREATE INDEX ix_resolution_plan_scope ON public.conversation_resolution_plans
  (creator_profile_id,fanvue_account_id,telegram_user_id,created_at DESC);
CREATE INDEX ix_resolution_events_plan ON public.conversation_resolution_events(plan_id,event_id);

COMMIT;
