BEGIN;
DROP TABLE IF EXISTS public.controlled_test_reset_audit;
ALTER TABLE public.ordinary_chat_reply_operations
    DROP COLUMN IF EXISTS inbound_received_at,
    DROP COLUMN IF EXISTS inbound_message_text;
COMMIT;
