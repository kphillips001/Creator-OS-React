BEGIN;

CREATE TABLE public.telegram_identity_map (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL
        REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    local_fanvue_user_id BIGINT NOT NULL
        REFERENCES public.fanvue_users(id) ON DELETE RESTRICT,
    external_fanvue_user_uuid UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT telegram_identity_map_telegram_user_unique
        UNIQUE (telegram_user_id),
    CONSTRAINT telegram_identity_map_canonical_user_unique
        UNIQUE (fanvue_account_id, local_fanvue_user_id),
    CONSTRAINT telegram_identity_map_commerce_user_unique
        UNIQUE (fanvue_account_id, external_fanvue_user_uuid),
    CONSTRAINT telegram_identity_map_telegram_user_positive
        CHECK (telegram_user_id > 0),
    CONSTRAINT telegram_identity_map_telegram_chat_nonzero
        CHECK (telegram_chat_id <> 0)
);

CREATE INDEX telegram_identity_map_active_telegram_lookup_idx
    ON public.telegram_identity_map (telegram_user_id)
    WHERE is_active = TRUE;

CREATE INDEX telegram_identity_map_active_canonical_lookup_idx
    ON public.telegram_identity_map (
        fanvue_account_id,
        local_fanvue_user_id
    )
    WHERE is_active = TRUE;

CREATE OR REPLACE FUNCTION public.validate_telegram_identity_canonical_user()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.fanvue_users fu
        WHERE fu.id = NEW.local_fanvue_user_id
          AND fu.fanvue_account_id = NEW.fanvue_account_id
          AND fu.fanvue_user_uuid =
              NEW.external_fanvue_user_uuid
    ) THEN
        RAISE EXCEPTION
            'Telegram identity must reference one matching canonical Fanvue user'
            USING ERRCODE = '23503';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER telegram_identity_canonical_user_guard
BEFORE INSERT OR UPDATE OF
    fanvue_account_id,
    local_fanvue_user_id,
    external_fanvue_user_uuid
ON public.telegram_identity_map
FOR EACH ROW
EXECUTE FUNCTION public.validate_telegram_identity_canonical_user();

CREATE OR REPLACE FUNCTION public.set_telegram_identity_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER telegram_identity_updated_at
BEFORE UPDATE ON public.telegram_identity_map
FOR EACH ROW
EXECUTE FUNCTION public.set_telegram_identity_updated_at();

COMMIT;

-- This migration is additive. Validate it on a disposable database before use.

