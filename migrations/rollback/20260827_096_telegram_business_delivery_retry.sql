UPDATE public.telegram_sales_delivery_operations
SET state='FAILED', failure_reason=COALESCE(
    failure_reason, 'rollback_from_retryable_business_delivery'
) WHERE state='RETRYABLE';
ALTER TABLE public.telegram_sales_delivery_operations
    DROP CONSTRAINT IF EXISTS telegram_sales_delivery_operations_state_check;
ALTER TABLE public.telegram_sales_delivery_operations
    ADD CONSTRAINT telegram_sales_delivery_operations_state_check
    CHECK (state IN (
        'CREATED','SENDING','TELEGRAM_ACCEPTED','CONFIRMED','FAILED','AMBIGUOUS'
    ));
