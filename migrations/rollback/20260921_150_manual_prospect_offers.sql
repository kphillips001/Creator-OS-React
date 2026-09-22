BEGIN;
-- Fails closed if unmapped prospect operations exist; never deletes evidence.
ALTER TABLE public.telegram_manual_offer_operations
 ALTER COLUMN telegram_identity_mapping_id SET NOT NULL,
 ALTER COLUMN local_fanvue_user_id SET NOT NULL,
 ALTER COLUMN conversation_thread_id SET NOT NULL,
 ALTER COLUMN business_connection_id SET NOT NULL,
 DROP COLUMN send_attempt_count;
ALTER TABLE public.telegram_sales_delivery_operations
 ALTER COLUMN conversation_thread_id SET NOT NULL,
 ALTER COLUMN fanvue_user_id SET NOT NULL;
COMMIT;
