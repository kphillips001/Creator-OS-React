ALTER TABLE public.telegram_sales_delivery_operations
    DROP CONSTRAINT IF EXISTS telegram_sales_delivery_operations_state_check;
ALTER TABLE public.telegram_sales_delivery_operations
    ADD CONSTRAINT telegram_sales_delivery_operations_state_check
    CHECK (state IN (
        'CREATED','RETRYABLE','SENDING','TELEGRAM_ACCEPTED',
        'CONFIRMED','FAILED','AMBIGUOUS'
    ));

DROP INDEX IF EXISTS public.idx_telegram_sales_delivery_incomplete;
CREATE INDEX idx_telegram_sales_delivery_incomplete
    ON public.telegram_sales_delivery_operations (state, updated_at)
    WHERE state IN ('CREATED','RETRYABLE','SENDING','TELEGRAM_ACCEPTED','AMBIGUOUS');
