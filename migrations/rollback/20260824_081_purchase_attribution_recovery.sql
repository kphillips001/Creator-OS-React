DROP TABLE IF EXISTS public.purchase_attribution_resolution_audit;
DROP INDEX IF EXISTS public.idx_commerce_signal_operator_review;
ALTER TABLE public.commerce_signal_reconciliations
    DROP CONSTRAINT IF EXISTS commerce_signal_reconciliations_attribution_state_check,
    DROP COLUMN IF EXISTS attributed_purchase_intent_id,
    DROP COLUMN IF EXISTS attribution_reason,
    DROP COLUMN IF EXISTS attribution_state;

