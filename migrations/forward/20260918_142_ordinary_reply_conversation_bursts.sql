BEGIN;

ALTER TABLE public.ordinary_chat_reply_operations
  ADD COLUMN IF NOT EXISTS conversation_burst_id UUID NULL,
  ADD COLUMN IF NOT EXISTS burst_role TEXT NULL,
  ADD COLUMN IF NOT EXISTS burst_survivor_operation_id UUID NULL,
  ADD COLUMN IF NOT EXISTS burst_freshness_telegram_message_id BIGINT NULL,
  ADD COLUMN IF NOT EXISTS burst_member_obligations JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS burst_obligations JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE public.ordinary_chat_reply_operations
  DROP CONSTRAINT IF EXISTS ordinary_reply_burst_role_check;
ALTER TABLE public.ordinary_chat_reply_operations
  ADD CONSTRAINT ordinary_reply_burst_role_check
  CHECK (burst_role IS NULL OR burst_role IN ('SURVIVOR','MEMBER'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_ordinary_reply_burst_survivor
  ON public.ordinary_chat_reply_operations (conversation_burst_id)
  WHERE conversation_burst_id IS NOT NULL AND burst_role='SURVIVOR';
CREATE INDEX IF NOT EXISTS idx_ordinary_reply_burst_members
  ON public.ordinary_chat_reply_operations (
    conversation_burst_id, inbound_telegram_message_id
  ) WHERE conversation_burst_id IS NOT NULL;

COMMIT;
