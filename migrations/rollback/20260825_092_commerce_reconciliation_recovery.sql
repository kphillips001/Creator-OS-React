BEGIN;
DROP TABLE IF EXISTS public.schema_migration_checksum_reconciliations;
DROP TABLE IF EXISTS public.provider_purchase_asset_ownership;
DROP TABLE IF EXISTS public.commerce_signal_reconciliation_evidence;
DROP INDEX IF EXISTS public.commerce_signal_reconciliation_claim_idx;
DROP INDEX IF EXISTS public.commerce_signal_reconciliation_transaction_family_uidx;
ALTER TABLE public.commerce_signal_reconciliations
    DROP CONSTRAINT IF EXISTS commerce_signal_reconciliations_max_attempts_check,
    DROP CONSTRAINT IF EXISTS commerce_signal_reconciliations_mode_check,
    DROP COLUMN IF EXISTS quarantined_at,
    DROP COLUMN IF EXISTS max_attempts,
    DROP COLUMN IF EXISTS lease_expires_at,
    DROP COLUMN IF EXISTS claimed_at,
    DROP COLUMN IF EXISTS claim_owner,
    DROP COLUMN IF EXISTS transaction_family_key,
    DROP COLUMN IF EXISTS reconciliation_mode;
DROP TABLE IF EXISTS public.commerce_backlog_recovery_items;
DROP TABLE IF EXISTS public.commerce_backlog_recovery_batches;
COMMIT;
