BEGIN;
ALTER TABLE public.telegram_manual_offer_operations
 ALTER COLUMN telegram_identity_mapping_id DROP NOT NULL,
 ALTER COLUMN local_fanvue_user_id DROP NOT NULL,
 ALTER COLUMN conversation_thread_id DROP NOT NULL,
 ALTER COLUMN business_connection_id DROP NOT NULL,
 ADD COLUMN send_attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(send_attempt_count>=0);
ALTER TABLE public.telegram_sales_delivery_operations
 ALTER COLUMN conversation_thread_id DROP NOT NULL,
 ALTER COLUMN fanvue_user_id DROP NOT NULL;
COMMIT;
