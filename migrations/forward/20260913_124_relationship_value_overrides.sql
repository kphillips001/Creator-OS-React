BEGIN;

CREATE TABLE public.telegram_relationship_value_overrides (
  override_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
  fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id),
  telegram_user_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  classification TEXT NOT NULL CHECK (classification = 'HIGH_VALUE_PROSPECT'),
  version BIGINT NOT NULL CHECK (version > 0),
  changed_by TEXT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason TEXT NULL,
  removed_by TEXT NULL,
  removed_at TIMESTAMPTZ NULL,
  CHECK ((removed_by IS NULL) = (removed_at IS NULL))
);

CREATE UNIQUE INDEX ux_relationship_value_override_active
  ON public.telegram_relationship_value_overrides(
    creator_profile_id, fanvue_account_id, telegram_user_id, telegram_chat_id
  ) WHERE removed_at IS NULL;

CREATE UNIQUE INDEX ux_relationship_value_override_version
  ON public.telegram_relationship_value_overrides(
    creator_profile_id, fanvue_account_id, telegram_user_id, telegram_chat_id, version
  );

CREATE INDEX ix_relationship_value_override_priority
  ON public.telegram_relationship_value_overrides(
    telegram_chat_id, telegram_user_id
  ) WHERE removed_at IS NULL AND classification = 'HIGH_VALUE_PROSPECT';

COMMIT;
