BEGIN;
CREATE TABLE public.canonical_relationship_facts (
 fact_id UUID PRIMARY KEY, creator_profile_id BIGINT NOT NULL REFERENCES creator_profiles(id) ON DELETE RESTRICT,
 fanvue_account_id BIGINT NOT NULL REFERENCES fanvue_accounts(id) ON DELETE RESTRICT,
 subject_type TEXT NOT NULL CHECK(subject_type IN ('CUSTOMER','CREATOR')),
 subject_id BIGINT NOT NULL, relation TEXT NOT NULL,
 object_type TEXT NOT NULL CHECK(object_type IN ('ENTITY','CONCEPT','ACTIVITY','CONTENT_PREFERENCE')),
 object_value TEXT NOT NULL, object_data JSONB NOT NULL DEFAULT '{}'::jsonb,
 attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
 category TEXT NOT NULL CHECK(category IN ('IDENTITY_CONTEXT','RELATIONSHIP','PREFERENCE','RECURRING_BEHAVIOR','CREATOR_SELF','SILENT_CONTEXT')),
 source_platform TEXT NOT NULL CHECK(source_platform IN ('FANVUE','TELEGRAM','X','CREATOR_OS','PROVIDER')),
 source_type TEXT NOT NULL CHECK(source_type IN ('OPERATOR_VERIFIED','FANVUE_CONVERSATION','TELEGRAM_CONVERSATION','X_OBSERVATION','CREATOR_CANONICAL','PROVIDER_VERIFIED')),
 source_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
 verification_method TEXT NOT NULL, confidence NUMERIC(4,3) NOT NULL CHECK(confidence>=0 AND confidence<=1),
 usage_policy TEXT NOT NULL CHECK(usage_policy IN ('NORMAL_CONTEXT','SILENT_CONTEXT')),
 observed_at TIMESTAMPTZ NULL, verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 state TEXT NOT NULL DEFAULT 'CURRENT' CHECK(state IN ('CURRENT','SUPERSEDED','INACTIVE')),
 superseded_by UUID NULL REFERENCES canonical_relationship_facts(fact_id) ON DELETE RESTRICT,
 correction_reason TEXT NULL, idempotency_key TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(creator_profile_id,idempotency_key)
);
CREATE UNIQUE INDEX canonical_relationship_fact_current_semantic_idx ON canonical_relationship_facts
(creator_profile_id,fanvue_account_id,subject_type,subject_id,relation,lower(object_value)) WHERE state='CURRENT';
CREATE INDEX canonical_relationship_fact_retrieval_idx ON canonical_relationship_facts
(creator_profile_id,fanvue_account_id,subject_type,subject_id,category,verified_at DESC) WHERE state='CURRENT';
CREATE TABLE public.canonical_relationship_fact_audit (
 audit_id UUID PRIMARY KEY, fact_id UUID NOT NULL REFERENCES canonical_relationship_facts(fact_id) ON DELETE RESTRICT,
 action TEXT NOT NULL CHECK(action IN ('CREATED','SUPERSEDED','DEACTIVATED')),
 operator_source TEXT NOT NULL, evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
