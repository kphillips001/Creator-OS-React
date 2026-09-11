CREATE TABLE public.telegram_business_peer_observations (
    observation_id UUID PRIMARY KEY,
    business_connection_id TEXT NOT NULL,
    telegram_peer_user_id BIGINT NOT NULL CHECK (telegram_peer_user_id > 0),
    telegram_chat_id BIGINT NOT NULL CHECK (telegram_chat_id > 0),
    telegram_message_id BIGINT NOT NULL CHECK (telegram_message_id > 0),
    bot_api_update_id BIGINT NOT NULL CHECK (bot_api_update_id >= 0),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'business_message','edited_business_message','deleted_business_messages'
    )),
    provider_timestamp TIMESTAMPTZ NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_business_inbound_at TIMESTAMPTZ NULL,
    sender_telegram_user_id BIGINT NULL CHECK (sender_telegram_user_id > 0),
    CONSTRAINT telegram_business_peer_connection_fkey
        FOREIGN KEY (business_connection_id)
        REFERENCES public.telegram_business_connections(business_connection_id)
        ON DELETE RESTRICT,
    CONSTRAINT telegram_business_peer_update_event_unique
        UNIQUE (bot_api_update_id,event_type,telegram_message_id)
);

CREATE UNIQUE INDEX telegram_business_peer_inbound_message_unique
    ON public.telegram_business_peer_observations (
        business_connection_id,telegram_chat_id,telegram_message_id
    ) WHERE event_type='business_message';

CREATE INDEX idx_telegram_business_peer_connection_chat
    ON public.telegram_business_peer_observations (
        business_connection_id,telegram_chat_id,observed_at DESC
    );

CREATE INDEX idx_telegram_business_peer_recent_inbound
    ON public.telegram_business_peer_observations (
        business_connection_id,telegram_peer_user_id,last_business_inbound_at DESC
    ) WHERE last_business_inbound_at IS NOT NULL;
