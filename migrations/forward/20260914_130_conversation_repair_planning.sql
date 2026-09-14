BEGIN;
CREATE TABLE public.conversation_repair_proposals(
 proposal_id UUID PRIMARY KEY,
 analysis_id UUID NOT NULL REFERENCES public.conversation_analyses(analysis_id) ON DELETE RESTRICT,
 finding_id TEXT NOT NULL,creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
 fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
 relationship_key TEXT NOT NULL,validated_scope TEXT NOT NULL CHECK(validated_scope IN('MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM')),
 root_cause_category TEXT NOT NULL,failure_signature TEXT NOT NULL,affected_relationship_count INTEGER NOT NULL CHECK(affected_relationship_count>=2),
 violated_invariant TEXT NOT NULL,proposed_invariant TEXT NOT NULL,expected_effect TEXT NOT NULL,
 preserved_behavior JSONB NOT NULL,known_risks JSONB NOT NULL,regression_requirements JSONB NOT NULL,
 repair_category TEXT NOT NULL CHECK(repair_category IN('COMMERCIAL_CLASSIFICATION_POLICY','COMMERCIAL_PROGRESSION_POLICY','SALES_BRAIN_POLICY','TURN_OBLIGATION_POLICY','QUALITY_GATE_POLICY','CONTEXT_ASSEMBLY_POLICY','MEMORY_RETRIEVAL_POLICY','TEMPORAL_CONTEXT_POLICY','AVAILABILITY_POLICY','DELIVERY_LIFECYCLE_POLICY','GENERATION_QUALITY_POLICY','TRAINING_EXAMPLE_ONLY','NO_REPAIR')),
 evidence_fingerprint TEXT NOT NULL CHECK(length(evidence_fingerprint)=64),risk TEXT NOT NULL CHECK(risk IN('LOW','MEDIUM','HIGH')),
 signature TEXT NOT NULL CHECK(length(signature)=64),status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK(status IN('PROPOSED','REJECTED','APPROVED_FOR_EXECUTION','EXPIRED','STALE')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),expires_at TIMESTAMPTZ NOT NULL,
 approved_by TEXT NULL,approved_at TIMESTAMPTZ NULL,rejected_by TEXT NULL,rejected_at TIMESTAMPTZ NULL,stale_reason TEXT NULL,
 UNIQUE(analysis_id,finding_id,evidence_fingerprint)
);
CREATE INDEX conversation_repair_proposals_scope_idx ON public.conversation_repair_proposals(creator_profile_id,fanvue_account_id,relationship_key,created_at DESC);
CREATE TABLE public.conversation_repair_execution_authorizations(
 authorization_id UUID PRIMARY KEY,proposal_id UUID NOT NULL UNIQUE REFERENCES public.conversation_repair_proposals(proposal_id) ON DELETE RESTRICT,
 repair_category TEXT NOT NULL,validated_scope TEXT NOT NULL,behavioral_invariant TEXT NOT NULL,
 regression_requirements JSONB NOT NULL,risk TEXT NOT NULL,evidence_fingerprint TEXT NOT NULL,
 approved_by TEXT NOT NULL,approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),expires_at TIMESTAMPTZ NOT NULL,consumed_at TIMESTAMPTZ NULL
);
CREATE TABLE public.conversation_repair_events(
 event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),proposal_id UUID NULL REFERENCES public.conversation_repair_proposals(proposal_id) ON DELETE RESTRICT,
 authorization_id UUID NULL REFERENCES public.conversation_repair_execution_authorizations(authorization_id) ON DELETE RESTRICT,
 event_type TEXT NOT NULL CHECK(event_type IN('PROPOSED','REJECTED','APPROVED','EXPIRED','STALE','EXECUTION_AUTHORIZED')),
 event_data JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
