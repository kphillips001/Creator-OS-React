ALTER TABLE public.commerce_signal_reconciliations
    ADD COLUMN IF NOT EXISTS attribution_state TEXT NULL,
    ADD COLUMN IF NOT EXISTS attribution_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS attributed_purchase_intent_id UUID NULL
        REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT;

ALTER TABLE public.commerce_signal_reconciliations
    DROP CONSTRAINT IF EXISTS commerce_signal_reconciliations_attribution_state_check;
ALTER TABLE public.commerce_signal_reconciliations
    ADD CONSTRAINT commerce_signal_reconciliations_attribution_state_check
    CHECK (attribution_state IS NULL OR attribution_state IN (
        'PENDING','UNKNOWN','ATTRIBUTED','MANUALLY_ATTRIBUTED'
    ));

CREATE INDEX IF NOT EXISTS idx_commerce_signal_operator_review
    ON public.commerce_signal_reconciliations (creator_profile_id,updated_at DESC)
    WHERE state='PENDING' OR attribution_state IN ('PENDING','UNKNOWN');

UPDATE public.commerce_signal_reconciliations reconciliation
SET attribution_state='ATTRIBUTED',
    attributed_purchase_intent_id=(
        SELECT intent.purchase_intent_id
        FROM public.purchase_intents intent
        WHERE intent.fanvue_account_id=reconciliation.fanvue_account_id
          AND intent.provider_transaction_order_id=COALESCE(
              reconciliation.canonical_transaction_order_id,
              reconciliation.observed_transaction_id)
          AND intent.status='PURCHASED'
          AND intent.attribution_result='ATTRIBUTED'
        LIMIT 1
    ),
    attribution_reason=COALESCE(
        attribution_reason,'Historical automatic attribution evidence backfilled.'
    )
WHERE reconciliation.state='VERIFIED'
  AND reconciliation.attribution_state IS NULL
  AND EXISTS (
      SELECT 1 FROM public.purchase_intents intent
      WHERE intent.fanvue_account_id=reconciliation.fanvue_account_id
        AND intent.provider_transaction_order_id=COALESCE(
            reconciliation.canonical_transaction_order_id,
            reconciliation.observed_transaction_id)
        AND intent.status='PURCHASED'
        AND intent.attribution_result='ATTRIBUTED'
  );

UPDATE public.commerce_signal_reconciliations
SET attribution_state='UNKNOWN',
    attribution_reason=COALESCE(
        attribution_reason,
        'Historical verified transaction has no durable attributed Purchase Intent.'
    )
WHERE state='VERIFIED' AND attribution_state IS NULL;

CREATE TABLE IF NOT EXISTS public.purchase_attribution_resolution_audit (
    resolution_id UUID PRIMARY KEY,
    reconciliation_id UUID NOT NULL UNIQUE
        REFERENCES public.commerce_signal_reconciliations(reconciliation_id) ON DELETE RESTRICT,
    fanvue_account_id BIGINT NOT NULL REFERENCES public.fanvue_accounts(id) ON DELETE RESTRICT,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    transaction_order_id TEXT NOT NULL,
    purchase_intent_id UUID NOT NULL REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE RESTRICT,
    commercial_offering_id UUID NOT NULL REFERENCES public.commercial_offerings(offering_id) ON DELETE RESTRICT,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL CHECK (new_state='MANUALLY_ATTRIBUTED'),
    resolution_type TEXT NOT NULL CHECK (resolution_type='MANUAL'),
    operator_source TEXT NOT NULL,
    operator_note TEXT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    downstream_completed_at TIMESTAMPTZ NULL,
    UNIQUE (fanvue_account_id,transaction_order_id)
);

ALTER TABLE public.purchase_attribution_resolution_audit
    ADD COLUMN IF NOT EXISTS downstream_completed_at TIMESTAMPTZ NULL;
