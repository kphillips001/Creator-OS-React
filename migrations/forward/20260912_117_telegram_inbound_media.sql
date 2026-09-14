BEGIN;

CREATE TABLE public.telegram_inbound_media_operations (
  operation_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  fanvue_account_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  telegram_user_id BIGINT NOT NULL,
  logical_turn_key TEXT NOT NULL,
  grouped_id TEXT NULL,
  caption_text TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL CHECK (state IN ('RECEIVED','DOWNLOADING','DOWNLOADED','VALIDATED','READY_FOR_ANALYSIS','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')),
  failure_category TEXT NULL,
  received_at TIMESTAMPTZ NULL,
  processing_started_at TIMESTAMPTZ NULL,
  ready_at TIMESTAMPTZ NULL,
  retention_expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (creator_profile_id,fanvue_account_id,logical_turn_key)
);

CREATE TABLE public.telegram_inbound_media_attachments (
  attachment_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL REFERENCES public.telegram_inbound_media_operations(operation_id) ON DELETE CASCADE,
  telegram_message_id BIGINT NOT NULL,
  telegram_media_id TEXT NOT NULL,
  media_kind TEXT NOT NULL CHECK (media_kind IN ('PHOTO','IMAGE_DOCUMENT')),
  grouped_id TEXT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  telegram_mime_type TEXT NULL,
  original_filename TEXT NULL,
  reported_size_bytes BIGINT NULL,
  reported_width INTEGER NULL,
  reported_height INTEGER NULL,
  actual_size_bytes BIGINT NULL,
  detected_format TEXT NULL,
  detected_mime_type TEXT NULL,
  decoded_width INTEGER NULL,
  decoded_height INTEGER NULL,
  normalized_path TEXT NULL,
  content_sha256 TEXT NULL,
  state TEXT NOT NULL CHECK (state IN ('RECEIVED','DOWNLOADING','DOWNLOADED','VALIDATED','READY_FOR_ANALYSIS','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')),
  failure_category TEXT NULL,
  downloaded_at TIMESTAMPTZ NULL,
  validated_at TIMESTAMPTZ NULL,
  ready_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (operation_id,telegram_message_id,telegram_media_id)
);

CREATE INDEX telegram_inbound_media_recovery_idx ON public.telegram_inbound_media_operations(state,updated_at);
CREATE INDEX telegram_inbound_media_retention_idx ON public.telegram_inbound_media_operations(retention_expires_at) WHERE retention_expires_at IS NOT NULL;
CREATE INDEX telegram_inbound_media_attachment_operation_idx ON public.telegram_inbound_media_attachments(operation_id,position);

COMMIT;
