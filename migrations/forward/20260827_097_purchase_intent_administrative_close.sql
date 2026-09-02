BEGIN;

ALTER TABLE public.purchase_intents
    DROP CONSTRAINT IF EXISTS purchase_intents_status_check;

ALTER TABLE public.purchase_intents
    ADD CONSTRAINT purchase_intents_status_check CHECK (
        status IN (
            'CREATED','PRESENTED','CLICKED','PURCHASED','EXPIRED',
            'ABANDONED','UNKNOWN','SUPERSEDED','ADMIN_CLOSED'
        )
    ),
    ADD COLUMN IF NOT EXISTS admin_closed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS administrative_close_reason TEXT NULL,
    ADD CONSTRAINT purchase_intents_admin_close_shape_check CHECK (
        (status = 'ADMIN_CLOSED') =
        (admin_closed_at IS NOT NULL AND
         BTRIM(administrative_close_reason) <> '')
    );

COMMIT;
