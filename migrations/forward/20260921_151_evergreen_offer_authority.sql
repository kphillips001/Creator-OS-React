BEGIN;
CREATE TABLE public.evergreen_offer_authorities (
 original_intent_id UUID PRIMARY KEY REFERENCES public.purchase_intents(purchase_intent_id),
 unlock_grant_id UUID NOT NULL UNIQUE REFERENCES public.telegram_unlock_grants(unlock_grant_id),
 fingerprint_reservation_id UUID UNIQUE REFERENCES public.fanvue_fingerprint_reservations(fingerprint_reservation_id),
 configured_price_minor BIGINT NOT NULL CHECK(configured_price_minor >= 0),
 final_price_minor BIGINT NOT NULL CHECK(final_price_minor >= 0),
 currency TEXT NOT NULL CHECK(currency ~ '^[A-Z]{3}$'),
 binding JSONB NOT NULL CHECK(jsonb_typeof(binding)='object'),
 media_uuids JSONB NOT NULL CHECK(jsonb_typeof(media_uuids)='array'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE FUNCTION public.guard_evergreen_offer_authority() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE i public.purchase_intents%ROWTYPE; r public.fanvue_fingerprint_reservations%ROWTYPE;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Evergreen offer authority is immutable'; END IF;
 SELECT * INTO STRICT i FROM public.purchase_intents WHERE purchase_intent_id=NEW.original_intent_id;
 IF NOT EXISTS(SELECT 1 FROM public.telegram_unlock_grants WHERE unlock_grant_id=NEW.unlock_grant_id AND purchase_intent_id=NEW.original_intent_id)
 OR NEW.configured_price_minor<>COALESCE(i.configured_base_price_minor,i.expected_price_minor)
 OR NEW.currency<>i.expected_currency THEN RAISE EXCEPTION 'Family binding/price mismatch'; END IF;
 IF NEW.binding IS DISTINCT FROM jsonb_build_object(
   'creator_profile_id',i.creator_profile_id::text,'fanvue_account_id',i.fanvue_account_id::text,
   'telegram_user_id',i.telegram_user_id::text,'telegram_chat_id',i.telegram_chat_id::text,
   'commercial_offering_id',i.commercial_offering_id::text,'commercial_publication_id',i.commercial_publication_id::text,
   'provider',i.provider,'provider_resource_id',i.provider_resource_id) THEN
  RAISE EXCEPTION 'Family commercial binding mismatch';
 END IF;
 IF NEW.fingerprint_reservation_id IS NOT NULL THEN
  SELECT * INTO STRICT r FROM public.fanvue_fingerprint_reservations WHERE fingerprint_reservation_id=NEW.fingerprint_reservation_id;
  IF r.purchase_intent_id<>NEW.original_intent_id OR r.exact_price_minor<>NEW.final_price_minor OR r.currency<>NEW.currency
  OR r.configured_base_price_minor<>NEW.configured_price_minor OR r.fanvue_account_id<>i.fanvue_account_id OR r.telegram_user_id<>i.telegram_user_id
  THEN RAISE EXCEPTION 'Family fingerprint mismatch'; END IF;
 ELSIF NEW.final_price_minor<>i.expected_price_minor OR i.telegram_identity_mapping_id IS NULL THEN
  RAISE EXCEPTION 'Family final price evidence missing';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_evergreen_offer_authority BEFORE INSERT OR UPDATE OR DELETE ON public.evergreen_offer_authorities
 FOR EACH ROW EXECUTE FUNCTION public.guard_evergreen_offer_authority();

CREATE TABLE public.evergreen_provider_operations (
 original_intent_id UUID PRIMARY KEY REFERENCES public.evergreen_offer_authorities(original_intent_id),
 operation_id UUID NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','INVOKING','UNKNOWN','READY')),
 attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 1),
 provider_resource_id TEXT,
 provider_evidence JSONB NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(provider_evidence)='array'),
 provider_url TEXT,
 reason_code TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK(state <> 'READY' OR (length(provider_resource_id)>0 AND length(provider_url)>0))
);
CREATE INDEX idx_evergreen_provider_reconciliation ON public.evergreen_provider_operations(state,updated_at);
ALTER TABLE public.evergreen_checkout_lineage ADD CONSTRAINT evergreen_price_immutable
 CHECK(predecessor_price_minor=successor_price_minor);
CREATE FUNCTION public.guard_evergreen_predecessor() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.evergreen_checkout_lineage WHERE namespace='creator-os-private-unlock' AND predecessor_id=OLD.purchase_intent_id) THEN
  RAISE EXCEPTION 'Evergreen predecessor is immutable history';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_evergreen_predecessor BEFORE UPDATE OR DELETE ON public.purchase_intents
 FOR EACH ROW EXECUTE FUNCTION public.guard_evergreen_predecessor();
CREATE FUNCTION public.guard_evergreen_fingerprint() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM public.evergreen_offer_authorities WHERE fingerprint_reservation_id=OLD.fingerprint_reservation_id)
 AND (NEW.exact_price_minor,NEW.currency,NEW.purchase_intent_id,NEW.configured_base_price_minor,NEW.fanvue_account_id,NEW.telegram_user_id)
 IS DISTINCT FROM (OLD.exact_price_minor,OLD.currency,OLD.purchase_intent_id,OLD.configured_base_price_minor,OLD.fanvue_account_id,OLD.telegram_user_id) THEN
  RAISE EXCEPTION 'Evergreen fingerprint authority is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_evergreen_fingerprint BEFORE UPDATE ON public.fanvue_fingerprint_reservations
 FOR EACH ROW EXECUTE FUNCTION public.guard_evergreen_fingerprint();
CREATE FUNCTION public.guard_evergreen_provider_operation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Provider invocation evidence cannot be deleted'; END IF;
 IF NEW.original_intent_id<>OLD.original_intent_id OR NEW.operation_id<>OLD.operation_id
 OR NOT(NEW.provider_evidence @> OLD.provider_evidence)
 OR NEW.attempt_count<OLD.attempt_count OR (OLD.state<>'PENDING' AND NEW.state='PENDING') THEN
  RAISE EXCEPTION 'Provider invocation identity/budget cannot be reset';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER guard_evergreen_provider_operation BEFORE UPDATE OR DELETE ON public.evergreen_provider_operations
 FOR EACH ROW EXECUTE FUNCTION public.guard_evergreen_provider_operation();
COMMIT;
