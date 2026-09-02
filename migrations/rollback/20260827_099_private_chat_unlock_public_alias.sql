BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.telegram_unlock_grants
        WHERE public_alias_hash IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: public Unlock aliases have been issued.';
    END IF;
END $$;

DROP INDEX IF EXISTS public.telegram_unlock_grants_public_alias_hash_uidx;
ALTER TABLE public.telegram_unlock_grants
    DROP CONSTRAINT IF EXISTS telegram_unlock_grants_public_alias_shape_check,
    DROP COLUMN IF EXISTS public_alias_generation,
    DROP COLUMN IF EXISTS public_alias_hash;

COMMIT;
