BEGIN;

-- The existing table retains its name so customer purchase history and foreign
-- keys survive the transition from perpetual lifecycle to bounded opportunity.
ALTER TABLE public.customer_photoshoot_lifecycles
  DROP CONSTRAINT IF EXISTS customer_photoshoot_lifecycles_status_check;

UPDATE public.customer_photoshoot_lifecycles
SET status = CASE
  WHEN status IN ('COMPLETED','DECLINED') THEN status
  WHEN status IN ('ABANDONED') THEN 'CLOSED'
  ELSE 'ACTIVE'
END;

ALTER TABLE public.customer_photoshoot_lifecycles
  ALTER COLUMN status SET DEFAULT 'ACTIVE',
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS finale_decision TEXT NOT NULL DEFAULT 'NOT_APPLICABLE',
  ADD COLUMN IF NOT EXISTS objection_attempts INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS objection_at TIMESTAMPTZ;

UPDATE public.customer_photoshoot_lifecycles
SET expires_at = COALESCE(expires_at, last_activity_at, created_at, NOW()) + INTERVAL '7 days'
WHERE status = 'ACTIVE';

-- Preserve the most recently active opportunity and close older concurrent
-- legacy rows before enforcing one active opportunity per customer.
WITH ranked AS (
  SELECT lifecycle_id, ROW_NUMBER() OVER (
    PARTITION BY creator_profile_id, customer_commerce_profile_id
    ORDER BY last_activity_at DESC NULLS LAST, created_at DESC, lifecycle_id
  ) AS position
  FROM public.customer_photoshoot_lifecycles
  WHERE status = 'ACTIVE'
)
UPDATE public.customer_photoshoot_lifecycles opportunity
SET status='CLOSED', closed_at=NOW(), updated_at=NOW()
FROM ranked
WHERE opportunity.lifecycle_id=ranked.lifecycle_id AND ranked.position>1;

ALTER TABLE public.customer_photoshoot_lifecycles
  ADD CONSTRAINT customer_photoshoot_lifecycles_status_check
    CHECK (status IN ('ACTIVE','OBJECTION','COMPLETED','CLOSED','DECLINED')),
  ADD CONSTRAINT customer_photoshoot_lifecycles_finale_decision_check
    CHECK (finale_decision IN ('NOT_APPLICABLE','PENDING','PURCHASED','DECLINED')),
  ADD CONSTRAINT customer_photoshoot_lifecycles_active_expiry_check
    CHECK (status NOT IN ('ACTIVE','OBJECTION') OR expires_at IS NOT NULL),
  ADD CONSTRAINT customer_photoshoot_lifecycles_objection_attempts_check
    CHECK (objection_attempts >= 0);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_active_photoshoot_opportunity
  ON public.customer_photoshoot_lifecycles (creator_profile_id, customer_commerce_profile_id)
  WHERE status IN ('ACTIVE','OBJECTION');

CREATE INDEX IF NOT EXISTS idx_customer_photoshoot_opportunity_expiry
  ON public.customer_photoshoot_lifecycles (expires_at)
  WHERE status IN ('ACTIVE','OBJECTION');

COMMIT;
