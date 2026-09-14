BEGIN;

ALTER TABLE public.telegram_identity_observations
  ADD COLUMN observation_sources TEXT[] NOT NULL DEFAULT ARRAY['PRIVATE_CHAT']::TEXT[],
  ADD COLUMN source_channel_id BIGINT NULL,
  ADD COLUMN private_chat_id BIGINT NULL,
  ADD COLUMN private_chat_observed_at TIMESTAMPTZ NULL,
  ADD COLUMN participant_status TEXT NULL;

UPDATE public.telegram_identity_observations
   SET private_chat_id=telegram_chat_id,
       private_chat_observed_at=COALESCE(last_observed_at,first_observed_at),
       observation_sources=ARRAY['PRIVATE_CHAT']::TEXT[];

ALTER TABLE public.telegram_identity_observations ALTER COLUMN telegram_chat_id DROP NOT NULL;
ALTER TABLE public.telegram_identity_observations
  ADD CONSTRAINT telegram_identity_observation_sources_check CHECK (
    cardinality(observation_sources)>0 AND
    observation_sources <@ ARRAY['BROADCAST_MEMBER','PRIVATE_CHAT']::TEXT[] AND
    ('PRIVATE_CHAT'=ANY(observation_sources))=(private_chat_id IS NOT NULL) AND
    ('BROADCAST_MEMBER'=ANY(observation_sources))=(source_channel_id IS NOT NULL)
  );

ALTER TABLE public.telegram_identity_map ALTER COLUMN telegram_chat_id DROP NOT NULL;

COMMIT;
