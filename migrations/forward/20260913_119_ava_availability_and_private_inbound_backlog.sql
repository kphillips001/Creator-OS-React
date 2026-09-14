BEGIN;

CREATE TABLE public.ava_availability_sessions (
  session_id UUID PRIMARY KEY,
  account_scope TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('AVAILABLE','ACTIVE','INTERMITTENT','BUSY','AWAY','SLEEPING')),
  started_at TIMESTAMPTZ NOT NULL,
  transition_at TIMESTAMPTZ NOT NULL CHECK (transition_at > started_at),
  daypart TEXT NOT NULL,
  transition_provenance TEXT NOT NULL,
  transition_reason TEXT NOT NULL,
  ended_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX uq_ava_availability_sessions_current
  ON public.ava_availability_sessions(account_scope) WHERE ended_at IS NULL;
CREATE INDEX idx_ava_availability_sessions_transition
  ON public.ava_availability_sessions(account_scope,transition_at) WHERE ended_at IS NULL;

CREATE TABLE public.telegram_private_inbound_messages (
  inbound_id UUID PRIMARY KEY,
  telegram_account_scope TEXT NOT NULL,
  telegram_user_id BIGINT NOT NULL CHECK (telegram_user_id > 0),
  telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id <> 0),
  telegram_message_id BIGINT NOT NULL CHECK (telegram_message_id > 0),
  received_at TIMESTAMPTZ NOT NULL,
  customer_text TEXT NOT NULL DEFAULT '',
  has_media BOOLEAN NOT NULL DEFAULT FALSE,
  media_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  creator_profile_id BIGINT NULL,
  fanvue_account_id BIGINT NULL,
  mapped_customer_id BIGINT NULL,
  prospect_id UUID NULL,
  ingestion_provenance TEXT NOT NULL,
  automation_state_at_receipt TEXT NOT NULL,
  reconciliation_state TEXT NOT NULL DEFAULT 'CAPTURED'
    CHECK (reconciliation_state IN ('CAPTURED','CLAIMED','RECONCILED','NO_RESPONSE_REQUIRED','SUPERSEDED','LIVE_HANDLED')),
  reconciliation_id UUID NULL,
  response_operation_id UUID NULL REFERENCES public.ordinary_chat_reply_operations(operation_id),
  reconciled_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_telegram_private_inbound_message_identity
    UNIQUE (telegram_account_scope,telegram_chat_id,telegram_message_id)
);
CREATE INDEX idx_telegram_private_inbound_backlog
  ON public.telegram_private_inbound_messages(
    telegram_account_scope,reconciliation_state,telegram_chat_id,received_at,telegram_message_id
  );
CREATE UNIQUE INDEX uq_telegram_private_inbound_reconciliation_operation
  ON public.telegram_private_inbound_messages(response_operation_id)
  WHERE response_operation_id IS NOT NULL;

COMMIT;
