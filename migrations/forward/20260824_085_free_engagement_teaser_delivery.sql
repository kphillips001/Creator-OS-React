BEGIN;

CREATE TABLE IF NOT EXISTS public.engagement_teaser_chat_controls (
    asset_id BIGINT PRIMARY KEY REFERENCES public.content_items(id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    chat_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.engagement_teaser_chat_controls (asset_id, creator_profile_id, chat_enabled)
SELECT destination.asset_id, asset.creator_profile_id, TRUE
FROM public.asset_content_destinations destination
JOIN public.content_items asset ON asset.id=destination.asset_id
WHERE destination.destination='TEASER'
  AND destination.metadata->>'purpose'='ENGAGEMENT_TEASER'
ON CONFLICT (asset_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.telegram_engagement_teaser_delivery_operations (
    operation_id UUID PRIMARY KEY,
    correlation_id TEXT NOT NULL UNIQUE CHECK (BTRIM(correlation_id)<>''),
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    fanvue_user_id BIGINT NOT NULL REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    conversation_thread_id BIGINT NOT NULL REFERENCES public.chat_threads(id) ON DELETE RESTRICT,
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id<>0),
    inbound_telegram_message_id BIGINT NULL,
    teaser_asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    media_reference TEXT NOT NULL CHECK (BTRIM(media_reference)<>''),
    caption TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'CREATED' CHECK (
        state IN ('CREATED','SENDING','TELEGRAM_ACCEPTED','CONFIRMED','FAILED','AMBIGUOUS')
    ),
    outbound_telegram_message_id BIGINT NULL,
    failure_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sending_at TIMESTAMPTZ NULL,
    telegram_accepted_at TIMESTAMPTZ NULL,
    confirmed_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT engagement_teaser_customer_asset_never_repeat UNIQUE (
        creator_profile_id, fanvue_account_id, fanvue_user_id, teaser_asset_id
    )
);

CREATE INDEX IF NOT EXISTS idx_engagement_teaser_delivery_incomplete
    ON public.telegram_engagement_teaser_delivery_operations (state, updated_at)
    WHERE state IN ('CREATED','SENDING','TELEGRAM_ACCEPTED','AMBIGUOUS');

CREATE INDEX IF NOT EXISTS idx_engagement_teaser_delivery_asset_usage
    ON public.telegram_engagement_teaser_delivery_operations (
        creator_profile_id, teaser_asset_id, telegram_accepted_at DESC
    );

COMMIT;
