BEGIN;

CREATE TABLE public.telegram_conversation_turn_reservations (
  reservation_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  fanvue_account_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  conversation_burst_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE SET NULL,
  opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closes_at TIMESTAMPTZ NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('OPEN','READY','CLAIMED','CLOSED','SUPERSEDED','CANCELLED')),
  member_inbound_ids UUID[] NOT NULL DEFAULT '{}',
  member_telegram_message_ids BIGINT[] NOT NULL DEFAULT '{}',
  member_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
  authoritative_response_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE SET NULL,
  newest_message_freshness_watermark BIGINT NOT NULL,
  version BIGINT NOT NULL DEFAULT 1,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (closes_at > opened_at)
);
CREATE UNIQUE INDEX uq_telegram_turn_reservation_open_peer
  ON public.telegram_conversation_turn_reservations(creator_profile_id,fanvue_account_id,telegram_chat_id)
  WHERE state='OPEN';
CREATE INDEX idx_telegram_turn_reservation_release
  ON public.telegram_conversation_turn_reservations(state,closes_at);

CREATE TABLE public.telegram_inbound_media_turns (
  media_turn_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  fanvue_account_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  media_operation_id UUID NOT NULL UNIQUE REFERENCES public.telegram_inbound_media_operations(operation_id) ON DELETE CASCADE,
  conversation_burst_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE SET NULL,
  authoritative_response_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE SET NULL,
  grouped_id TEXT NULL,
  member_inbound_ids UUID[] NOT NULL DEFAULT '{}',
  member_telegram_message_ids BIGINT[] NOT NULL DEFAULT '{}',
  member_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
  newest_message_freshness_watermark BIGINT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('OPEN','BOUND','RESPONDED','SUPERSEDED','FAILED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_telegram_media_turn_open_peer
  ON public.telegram_inbound_media_turns(creator_profile_id,fanvue_account_id,telegram_chat_id,state,updated_at DESC)
  WHERE state IN ('OPEN','BOUND');

CREATE TABLE public.telegram_inbound_visual_turn_summaries (
  summary_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  fanvue_account_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  media_turn_id UUID NOT NULL UNIQUE REFERENCES public.telegram_inbound_media_turns(media_turn_id) ON DELETE CASCADE,
  media_operation_id UUID NOT NULL UNIQUE REFERENCES public.telegram_inbound_media_operations(operation_id) ON DELETE CASCADE,
  conversation_burst_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id) ON DELETE SET NULL,
  source_attachment_ids UUID[] NOT NULL,
  schema_version TEXT NOT NULL,
  sanitized_summary JSONB NOT NULL,
  aggregate_confidence NUMERIC(5,4) NULL CHECK (aggregate_confidence IS NULL OR aggregate_confidence BETWEEN 0 AND 1),
  identity_authority BOOLEAN NOT NULL DEFAULT FALSE CHECK (identity_authority=FALSE),
  sensitive_inference_authority BOOLEAN NOT NULL DEFAULT FALSE CHECK (sensitive_inference_authority=FALSE),
  raw_provider_output_persisted BOOLEAN NOT NULL DEFAULT FALSE CHECK (raw_provider_output_persisted=FALSE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  CHECK (expires_at > created_at)
);

CREATE INDEX idx_telegram_visual_summary_live_peer
  ON public.telegram_inbound_visual_turn_summaries(creator_profile_id,fanvue_account_id,telegram_chat_id,expires_at DESC);

COMMIT;
