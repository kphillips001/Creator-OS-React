BEGIN;

CREATE TABLE public.market_tier_confirmed_reply_events (
  event_id UUID PRIMARY KEY,
  operation_id UUID NOT NULL UNIQUE REFERENCES public.ordinary_chat_reply_operations(operation_id),
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
  fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id),
  telegram_user_id BIGINT NOT NULL,
  telegram_chat_id BIGINT NOT NULL,
  resource_classification TEXT NOT NULL CHECK (resource_classification = 'ORDINARY_NONCOMMERCIAL'),
  outbound_telegram_message_id BIGINT NOT NULL,
  confirmed_at TIMESTAMPTZ NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_market_tier_confirmed_reply_day
  ON public.market_tier_confirmed_reply_events(
    creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,confirmed_at
  );

COMMIT;
