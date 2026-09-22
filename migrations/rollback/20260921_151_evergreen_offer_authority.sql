BEGIN;
-- Runtime rollback must first disable the feature. Do not discard live evidence.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM public.evergreen_offer_authorities) THEN
  RAISE EXCEPTION 'Cannot roll back populated evergreen authority; preserve settlement evidence';
 END IF;
END $$;
DROP TRIGGER guard_evergreen_predecessor ON public.purchase_intents;
DROP FUNCTION public.guard_evergreen_predecessor();
DROP TRIGGER guard_evergreen_fingerprint ON public.fanvue_fingerprint_reservations;
DROP FUNCTION public.guard_evergreen_fingerprint();
ALTER TABLE public.evergreen_checkout_lineage DROP CONSTRAINT evergreen_price_immutable;
DROP TABLE public.evergreen_provider_operations;
DROP FUNCTION public.guard_evergreen_provider_operation();
DROP TABLE public.evergreen_offer_authorities;
DROP FUNCTION public.guard_evergreen_offer_authority();
COMMIT;
