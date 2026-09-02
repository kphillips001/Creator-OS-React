CREATE TABLE IF NOT EXISTS public.telegram_business_connections (
    business_connection_id TEXT PRIMARY KEY CHECK (BTRIM(business_connection_id) <> ''),
    business_owner_telegram_user_id BIGINT NOT NULL CHECK (business_owner_telegram_user_id > 0),
    bot_telegram_user_id BIGINT NOT NULL CHECK (bot_telegram_user_id > 0),
    is_enabled BOOLEAN NOT NULL,
    can_reply BOOLEAN NOT NULL,
    rights JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_updated_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_business_connection_active
    ON public.telegram_business_connections (
        business_owner_telegram_user_id, bot_telegram_user_id
    ) WHERE superseded_at IS NULL;
