BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.purchase_intents WHERE status='ADMIN_CLOSED'
    ) THEN
        RAISE EXCEPTION 'Cannot roll back: ADMIN_CLOSED PurchaseIntents exist';
    END IF;
END $$;

ALTER TABLE public.purchase_intents
    DROP CONSTRAINT IF EXISTS purchase_intents_admin_close_shape_check,
    DROP COLUMN IF EXISTS administrative_close_reason,
    DROP COLUMN IF EXISTS admin_closed_at,
    DROP CONSTRAINT IF EXISTS purchase_intents_status_check;

ALTER TABLE public.purchase_intents
    ADD CONSTRAINT purchase_intents_status_check CHECK (
        status IN (
            'CREATED','PRESENTED','CLICKED','PURCHASED','EXPIRED',
            'ABANDONED','UNKNOWN','SUPERSEDED'
        )
    );

COMMIT;
