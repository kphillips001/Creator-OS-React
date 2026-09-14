BEGIN;

DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM public.telegram_identity_observations WHERE private_chat_id IS NULL) THEN
  RAISE EXCEPTION 'Rollback blocked: broadcast-only Telegram observations exist';
 END IF;
END $$;

UPDATE public.telegram_identity_observations SET telegram_chat_id=private_chat_id;
ALTER TABLE public.telegram_identity_observations ALTER COLUMN telegram_chat_id SET NOT NULL;
ALTER TABLE public.telegram_identity_map ALTER COLUMN telegram_chat_id SET NOT NULL;
ALTER TABLE public.telegram_identity_observations
  DROP CONSTRAINT IF EXISTS telegram_identity_observation_sources_check,
  DROP COLUMN participant_status,
  DROP COLUMN private_chat_observed_at,
  DROP COLUMN private_chat_id,
  DROP COLUMN source_channel_id,
  DROP COLUMN observation_sources;

COMMIT;
