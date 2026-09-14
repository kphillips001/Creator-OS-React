BEGIN;

CREATE TABLE public.conversation_analyses (
  analysis_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
  fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
  relationship_key TEXT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('CONVERSATION','TURN')),
  target_message_reference TEXT NULL,
  evidence_fingerprint TEXT NOT NULL CHECK (length(evidence_fingerprint)=64),
  evidence_digest TEXT NOT NULL CHECK (length(evidence_digest)=64),
  structured_result JSONB NOT NULL,
  validated_scope TEXT NOT NULL CHECK (validated_scope IN (
    'CONVERSATION_ONLY','MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM','OBSOLETE','AMBIGUOUS')),
  failure_signatures JSONB NOT NULL DEFAULT '[]'::jsonb,
  similar_case_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  global_repair_candidate BOOLEAN NOT NULL DEFAULT FALSE,
  provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  schema_version TEXT NOT NULL,
  analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (jsonb_typeof(structured_result)='object'),
  CHECK (jsonb_typeof(failure_signatures)='array'),
  CHECK (jsonb_typeof(similar_case_summary)='object'),
  CHECK (jsonb_typeof(provider_metadata)='object')
);

CREATE INDEX conversation_analyses_scope_idx ON public.conversation_analyses(
  creator_profile_id,fanvue_account_id,relationship_key,analyzed_at DESC);
CREATE INDEX conversation_analyses_signatures_idx ON public.conversation_analyses
  USING GIN(failure_signatures);

COMMIT;
