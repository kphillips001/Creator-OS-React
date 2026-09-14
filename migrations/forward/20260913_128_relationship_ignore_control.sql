BEGIN;

ALTER TABLE public.telegram_relationship_controls
  ADD COLUMN communication_disposition TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK (communication_disposition IN ('ACTIVE','IGNORED')),
  ADD COLUMN ignore_version BIGINT NOT NULL DEFAULT 0 CHECK (ignore_version >= 0),
  ADD COLUMN ignored_at TIMESTAMPTZ NULL,
  ADD COLUMN ignored_by TEXT NULL,
  ADD COLUMN ignore_reason TEXT NULL,
  ADD COLUMN unignored_at TIMESTAMPTZ NULL,
  ADD COLUMN unignored_by TEXT NULL,
  ADD COLUMN resume_after_inbound_message_id BIGINT NULL;

CREATE TABLE public.telegram_relationship_ignore_events (
  event_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
  fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
  telegram_user_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('IGNORED','UNIGNORED')),
  ignore_version BIGINT NOT NULL CHECK (ignore_version > 0),
  control_version BIGINT NOT NULL CHECK (control_version > 0),
  changed_by TEXT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason TEXT NULL,
  resume_after_inbound_message_id BIGINT NULL,
  neutralization_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (creator_profile_id,fanvue_account_id,telegram_user_id,ignore_version)
);

CREATE INDEX telegram_relationship_ignore_events_scope_idx
  ON public.telegram_relationship_ignore_events(
    creator_profile_id,fanvue_account_id,telegram_user_id,changed_at DESC);

ALTER TABLE public.telegram_sales_delivery_operations
  DROP CONSTRAINT IF EXISTS telegram_sales_delivery_operations_state_check;
ALTER TABLE public.telegram_sales_delivery_operations
  ADD CONSTRAINT telegram_sales_delivery_operations_state_check CHECK (state IN (
    'CREATED','RETRYABLE','SENDING','TELEGRAM_ACCEPTED','CONFIRMED','FAILED','AMBIGUOUS','SUPPRESSED'));

COMMIT;
