BEGIN;

DROP INDEX IF EXISTS public.purchase_intents_one_unresolved_telegram_customer_idx;

DROP TABLE IF EXISTS public.fanvue_runtime_media_link_operations;
DROP TABLE IF EXISTS public.fanvue_runtime_media_links;
DROP TABLE IF EXISTS public.fanvue_fingerprint_reservations;
DROP TABLE IF EXISTS public.telegram_unlock_grants;
DROP TABLE IF EXISTS public.telegram_provisional_sales_sessions;
DROP TABLE IF EXISTS public.telegram_sales_prospects;

ALTER TABLE public.purchase_intents
    DROP CONSTRAINT IF EXISTS purchase_intents_mapping_bootstrap_consistency,
    DROP CONSTRAINT IF EXISTS purchase_intents_bootstrap_mode_check,
    DROP COLUMN IF EXISTS actual_charged_price_minor,
    DROP COLUMN IF EXISTS configured_base_price_minor,
    DROP COLUMN IF EXISTS identity_bootstrap_mode;

ALTER TABLE public.purchase_intents
    ALTER COLUMN telegram_identity_mapping_id SET NOT NULL;

COMMIT;
