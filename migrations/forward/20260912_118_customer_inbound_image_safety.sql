BEGIN;

ALTER TABLE public.telegram_inbound_media_operations
  DROP CONSTRAINT telegram_inbound_media_operations_state_check,
  ADD CONSTRAINT telegram_inbound_media_operations_state_check CHECK (state IN (
    'RECEIVED','DOWNLOADING','DOWNLOADED','VALIDATED','READY_FOR_ANALYSIS',
    'SAFETY_ANALYZING','SAFETY_CLASSIFIED','SAFETY_FAILED',
    'UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')),
  ADD COLUMN album_finalize_after TIMESTAMPTZ NULL,
  ADD COLUMN finalized_at TIMESTAMPTZ NULL,
  ADD COLUMN safety_started_at TIMESTAMPTZ NULL,
  ADD COLUMN safety_classified_at TIMESTAMPTZ NULL,
  ADD COLUMN safety_state TEXT NULL CHECK (safety_state IS NULL OR safety_state IN (
    'NORMAL_NON_EXPLICIT','SUGGESTIVE_NON_EXPLICIT','NUDITY_NON_GENITAL',
    'EXPLICIT_GENITAL','AMBIGUOUS_REVIEW_REQUIRED','UNCLASSIFIABLE')),
  ADD COLUMN solicitation_state TEXT NULL CHECK (solicitation_state IS NULL OR solicitation_state IN ('CLEARLY_SOLICITED','UNSOLICITED')),
  ADD COLUMN response_policy TEXT NULL CHECK (response_policy IS NULL OR response_policy IN (
    'NORMAL_VISUAL_RESPONSE_ALLOWED','SELFIE_COMPLIMENT_ELIGIBLE','SUGGESTIVE_VISUAL_RESPONSE',
    'NUDITY_RESPONSE_REQUIRED','POLITE_EXPLICIT_BOUNDARY','FIRM_EXPLICIT_BOUNDARY',
    'SOLICITED_EXPLICIT_MEDIA','AMBIGUOUS_SAFE_RESPONSE','UNCLASSIFIABLE_SAFE_RESPONSE')),
  ADD COLUMN partial_failure BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE public.telegram_inbound_media_safety_results (
  safety_result_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL REFERENCES public.telegram_inbound_media_operations(operation_id) ON DELETE CASCADE,
  attachment_id UUID NOT NULL REFERENCES public.telegram_inbound_media_attachments(attachment_id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  safety_state TEXT NOT NULL CHECK (safety_state IN (
    'NORMAL_NON_EXPLICIT','SUGGESTIVE_NON_EXPLICIT','NUDITY_NON_GENITAL',
    'EXPLICIT_GENITAL','AMBIGUOUS_REVIEW_REQUIRED','UNCLASSIFIABLE')),
  classifier TEXT NOT NULL,
  classifier_version TEXT NOT NULL,
  relevant_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
  classified_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (attachment_id)
);

CREATE TABLE public.telegram_explicit_boundary_events (
  boundary_event_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL UNIQUE REFERENCES public.telegram_inbound_media_operations(operation_id) ON DELETE CASCADE,
  creator_profile_id BIGINT NOT NULL,
  fanvue_account_id BIGINT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  policy TEXT NOT NULL CHECK (policy IN ('POLITE_EXPLICIT_BOUNDARY','FIRM_EXPLICIT_BOUNDARY')),
  delivered_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX telegram_inbound_media_safety_recovery_idx
  ON public.telegram_inbound_media_operations(state,album_finalize_after,updated_at)
  WHERE state IN ('READY_FOR_ANALYSIS','SAFETY_ANALYZING','SAFETY_FAILED');
CREATE INDEX telegram_inbound_media_safety_operation_idx
  ON public.telegram_inbound_media_safety_results(operation_id,position);
CREATE INDEX telegram_explicit_boundary_lookup_idx
  ON public.telegram_explicit_boundary_events(creator_profile_id,fanvue_account_id,telegram_user_id,delivered_at DESC);

COMMIT;
