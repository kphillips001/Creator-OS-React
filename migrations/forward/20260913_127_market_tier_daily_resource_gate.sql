BEGIN;
CREATE TABLE public.market_tier_daily_budgets (
 budget_id UUID PRIMARY KEY, creator_profile_id BIGINT NOT NULL REFERENCES creator_profiles(id),
 fanvue_account_id BIGINT NOT NULL REFERENCES fanvue_accounts(id), telegram_user_id BIGINT NOT NULL,
 telegram_chat_id BIGINT NOT NULL, business_date DATE NOT NULL, market_tier TEXT NOT NULL CHECK(market_tier='MEDIUM'),
 daily_reply_budget INTEGER NOT NULL CHECK(daily_reply_budget BETWEEN 5 AND 10),
 business_day_start TIMESTAMPTZ NOT NULL,business_day_end TIMESTAMPTZ NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,business_date));
CREATE TABLE public.market_tier_resource_policy_events (
 event_id UUID PRIMARY KEY,idempotency_key TEXT NOT NULL UNIQUE,operation_id UUID NULL REFERENCES ordinary_chat_reply_operations(operation_id),
 creator_profile_id BIGINT NOT NULL REFERENCES creator_profiles(id),fanvue_account_id BIGINT NOT NULL REFERENCES fanvue_accounts(id),
 telegram_user_id BIGINT NOT NULL,telegram_chat_id BIGINT NOT NULL,event_type TEXT NOT NULL,
 evidence JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE INDEX ix_market_tier_policy_events_scope ON public.market_tier_resource_policy_events(creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,created_at);
COMMIT;
