BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.telegram_provisional_sales_sessions
        WHERE state='ADMIN_CLOSED'
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: ADMIN_CLOSED provisional Session history exists.';
    END IF;
END $$;

ALTER TABLE public.telegram_provisional_sales_sessions
    DROP CONSTRAINT IF EXISTS telegram_provisional_sales_sessions_admin_close_shape;
ALTER TABLE public.telegram_provisional_sales_sessions
    DROP CONSTRAINT IF EXISTS telegram_provisional_sales_sessions_state_check;
ALTER TABLE public.telegram_provisional_sales_sessions
    ADD CONSTRAINT telegram_provisional_sales_sessions_state_check CHECK (
        state IN (
            'ACTIVE','OFFERING','AWAITING_PAYMENT','GRADUATED',
            'EXPIRED','ABANDONED'
        )
    );
ALTER TABLE public.telegram_provisional_sales_sessions
    DROP COLUMN IF EXISTS administratively_closed_at,
    DROP COLUMN IF EXISTS administrative_close_reason;

COMMIT;
