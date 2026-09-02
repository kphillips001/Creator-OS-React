BEGIN;
DROP INDEX IF EXISTS public.idx_telegram_sales_delivery_purchase_intent;
-- Restoring uniqueness is unsafe after lifecycle deliveries exist.
COMMIT;
