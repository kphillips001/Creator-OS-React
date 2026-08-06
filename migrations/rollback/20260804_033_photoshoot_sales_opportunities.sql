BEGIN;
DROP INDEX IF EXISTS public.idx_customer_photoshoot_opportunity_expiry;
DROP INDEX IF EXISTS public.uq_customer_active_photoshoot_opportunity;
ALTER TABLE public.customer_photoshoot_lifecycles
  DROP CONSTRAINT IF EXISTS customer_photoshoot_lifecycles_active_expiry_check,
  DROP CONSTRAINT IF EXISTS customer_photoshoot_lifecycles_objection_attempts_check,
  DROP CONSTRAINT IF EXISTS customer_photoshoot_lifecycles_finale_decision_check,
  DROP CONSTRAINT IF EXISTS customer_photoshoot_lifecycles_status_check;
UPDATE public.customer_photoshoot_lifecycles SET status='ABANDONED' WHERE status='CLOSED';
ALTER TABLE public.customer_photoshoot_lifecycles
  ALTER COLUMN status SET DEFAULT 'NEVER_STARTED',
  ADD CONSTRAINT customer_photoshoot_lifecycles_status_check
    CHECK(status IN ('NEVER_STARTED','INTRODUCED','ACTIVE','PAUSED','STALLED','COMPLETED','ABANDONED','DECLINED')),
  DROP COLUMN IF EXISTS finale_decision,
  DROP COLUMN IF EXISTS objection_attempts,
  DROP COLUMN IF EXISTS objection_at,
  DROP COLUMN IF EXISTS closed_at,
  DROP COLUMN IF EXISTS expires_at;
COMMIT;
