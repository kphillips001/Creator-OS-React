BEGIN;

CREATE TABLE public.telegram_relationship_market_tiers (
  market_tier_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
  fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id),
  telegram_user_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  market_tier TEXT NOT NULL CHECK (market_tier IN ('HIGH','MEDIUM','LOW')),
  version BIGINT NOT NULL CHECK (version > 0),
  changed_by TEXT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason TEXT NULL,
  removed_by TEXT NULL,
  removed_at TIMESTAMPTZ NULL,
  replaced_by UUID NULL REFERENCES public.telegram_relationship_market_tiers(market_tier_id)
    DEFERRABLE INITIALLY DEFERRED,
  CHECK ((removed_by IS NULL) = (removed_at IS NULL)),
  CHECK (replaced_by IS NULL OR removed_at IS NOT NULL)
);

CREATE UNIQUE INDEX ux_relationship_market_tier_active
  ON public.telegram_relationship_market_tiers(
    creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id
  ) WHERE removed_at IS NULL;

CREATE UNIQUE INDEX ux_relationship_market_tier_version
  ON public.telegram_relationship_market_tiers(
    creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,version
  );

COMMIT;
