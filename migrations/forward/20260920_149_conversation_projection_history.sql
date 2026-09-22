-- Observation history only: never rewrites operations or enrolls historical work.
CREATE TABLE public.conversation_projection_events (
 event_id BIGSERIAL PRIMARY KEY,
 creator_profile_id BIGINT NOT NULL,
 fanvue_account_id BIGINT NOT NULL,
 telegram_user_id BIGINT NOT NULL,
 telegram_chat_id BIGINT NOT NULL,
 projection_hash TEXT NOT NULL CHECK (length(projection_hash)=64),
 projection JSONB NOT NULL CHECK (jsonb_typeof(projection)='object'),
 observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX conversation_projection_events_relationship_idx ON public.conversation_projection_events
 (creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,event_id DESC);

-- Optional route hint; the actual capability/reachability decision is authoritative.
ALTER TABLE public.telegram_manual_offer_operations ALTER COLUMN business_connection_id DROP NOT NULL;
