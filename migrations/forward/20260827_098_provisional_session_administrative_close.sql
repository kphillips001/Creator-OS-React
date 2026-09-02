BEGIN;

ALTER TABLE public.telegram_provisional_sales_sessions
    DROP CONSTRAINT IF EXISTS telegram_provisional_sales_sessions_state_check;

ALTER TABLE public.telegram_provisional_sales_sessions
    ADD CONSTRAINT telegram_provisional_sales_sessions_state_check CHECK (
        state IN (
            'ACTIVE','OFFERING','AWAITING_PAYMENT','GRADUATED',
            'EXPIRED','ABANDONED','ADMIN_CLOSED'
        )
    );

ALTER TABLE public.telegram_provisional_sales_sessions
    ADD COLUMN IF NOT EXISTS administratively_closed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS administrative_close_reason TEXT NULL;

ALTER TABLE public.telegram_provisional_sales_sessions
    ADD CONSTRAINT telegram_provisional_sales_sessions_admin_close_shape CHECK (
        (state='ADMIN_CLOSED') = (
            administratively_closed_at IS NOT NULL
            AND BTRIM(administrative_close_reason) <> ''
        )
    ) NOT VALID;

UPDATE public.telegram_provisional_sales_sessions session
SET state='ADMIN_CLOSED',
    administratively_closed_at=COALESCE(
        intent.admin_closed_at,session.updated_at,NOW()
    ),
    administrative_close_reason=COALESCE(
        NULLIF(BTRIM(intent.administrative_close_reason),''),
        'BOUND_INTENT_ADMIN_CLOSED'
    ),
    updated_at=NOW()
FROM public.purchase_intents intent
WHERE intent.purchase_intent_id=session.first_purchase_intent_id
  AND intent.status='ADMIN_CLOSED'
  AND session.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT');

ALTER TABLE public.telegram_provisional_sales_sessions
    VALIDATE CONSTRAINT telegram_provisional_sales_sessions_admin_close_shape;

COMMIT;
