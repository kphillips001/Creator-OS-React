BEGIN;
ALTER TABLE public.telegram_sales_delivery_operations
 ADD COLUMN manual_offer_operation_id UUID REFERENCES public.telegram_manual_offer_operations(operation_id),
 ALTER COLUMN inbound_telegram_message_id DROP NOT NULL,
 ADD CONSTRAINT sales_delivery_manual_anchor_unique UNIQUE (manual_offer_operation_id),
 ADD CONSTRAINT sales_delivery_exactly_one_anchor CHECK (
   (inbound_telegram_message_id IS NOT NULL AND manual_offer_operation_id IS NULL)
   OR (inbound_telegram_message_id IS NULL AND manual_offer_operation_id IS NOT NULL));
-- The existing (chat,inbound) UNIQUE constraint is deliberately untouched.
CREATE FUNCTION public.guard_sales_delivery_anchor() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
  IF ROW(NEW.telegram_chat_id,NEW.inbound_telegram_message_id,NEW.manual_offer_operation_id,
         NEW.purchase_intent_id,NEW.correlation_id)
     IS DISTINCT FROM ROW(OLD.telegram_chat_id,OLD.inbound_telegram_message_id,OLD.manual_offer_operation_id,
         OLD.purchase_intent_id,OLD.correlation_id) THEN
   RAISE EXCEPTION 'Sales delivery anchor is immutable';
  END IF;
 ELSIF NEW.manual_offer_operation_id IS NOT NULL THEN
  IF NOT EXISTS (
   SELECT 1 FROM public.telegram_manual_offer_operations m JOIN public.purchase_intents p
    ON p.purchase_intent_id=m.purchase_intent_id
   WHERE m.operation_id=NEW.manual_offer_operation_id AND m.state='SENDING'
    AND m.purchase_intent_id=NEW.purchase_intent_id
    AND m.creator_profile_id=NEW.creator_profile_id AND m.fanvue_account_id=NEW.fanvue_account_id
    AND m.telegram_chat_id=NEW.telegram_chat_id
    AND m.commercial_offering_id=NEW.commercial_offering_id
    AND m.commercial_publication_id=NEW.commercial_publication_id
    AND p.telegram_chat_id=m.telegram_chat_id AND p.telegram_user_id=m.telegram_user_id
    AND p.creator_profile_id=m.creator_profile_id AND p.fanvue_account_id=m.fanvue_account_id
    AND p.commercial_offering_id=m.commercial_offering_id
    AND p.commercial_publication_id=m.commercial_publication_id
  ) THEN RAISE EXCEPTION 'Persisted manual offer anchor authority required'; END IF;
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER guard_sales_delivery_anchor BEFORE INSERT OR UPDATE
 ON public.telegram_sales_delivery_operations FOR EACH ROW EXECUTE FUNCTION public.guard_sales_delivery_anchor();
COMMIT;
