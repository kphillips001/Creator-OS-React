BEGIN;

DROP INDEX IF EXISTS public.idx_commercial_publications_fulfillment;
ALTER TABLE public.commercial_publications
    DROP CONSTRAINT IF EXISTS commercial_publications_provider_resource_status_check,
    DROP COLUMN IF EXISTS reconciliation_result,
    DROP COLUMN IF EXISTS last_reconciled_at,
    DROP COLUMN IF EXISTS provider_resource_status;

COMMIT;
