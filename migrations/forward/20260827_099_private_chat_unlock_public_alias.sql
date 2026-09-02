BEGIN;

ALTER TABLE public.telegram_unlock_grants
    ADD COLUMN IF NOT EXISTS public_alias_hash TEXT NULL,
    ADD COLUMN IF NOT EXISTS public_alias_generation SMALLINT NULL;

ALTER TABLE public.telegram_unlock_grants
    DROP CONSTRAINT IF EXISTS telegram_unlock_grants_public_alias_shape_check;

ALTER TABLE public.telegram_unlock_grants
    ADD CONSTRAINT telegram_unlock_grants_public_alias_shape_check CHECK (
        (public_alias_hash IS NULL AND public_alias_generation IS NULL)
        OR (
            public_alias_hash ~ '^[0-9a-f]{64}$'
            AND public_alias_generation BETWEEN 0 AND 4
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS telegram_unlock_grants_public_alias_hash_uidx
    ON public.telegram_unlock_grants (public_alias_hash)
    WHERE public_alias_hash IS NOT NULL;

COMMIT;
