BEGIN;

DROP TABLE IF EXISTS public.telegram_identity_map;

DROP FUNCTION IF EXISTS public.set_telegram_identity_updated_at();
DROP FUNCTION IF EXISTS public.validate_telegram_identity_canonical_user();

COMMIT;
