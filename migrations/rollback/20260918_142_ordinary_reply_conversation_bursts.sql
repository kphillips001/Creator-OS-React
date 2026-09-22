BEGIN;

DROP INDEX IF EXISTS public.idx_ordinary_reply_burst_members;
DROP INDEX IF EXISTS public.uq_ordinary_reply_burst_survivor;
ALTER TABLE public.ordinary_chat_reply_operations
  DROP CONSTRAINT IF EXISTS ordinary_reply_burst_role_check,
  DROP COLUMN IF EXISTS burst_obligations,
  DROP COLUMN IF EXISTS burst_member_obligations,
  DROP COLUMN IF EXISTS burst_freshness_telegram_message_id,
  DROP COLUMN IF EXISTS burst_survivor_operation_id,
  DROP COLUMN IF EXISTS burst_role,
  DROP COLUMN IF EXISTS conversation_burst_id;

COMMIT;
