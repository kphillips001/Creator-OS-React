CREATE TABLE public.active_offer_follow_through_events (
 event_id UUID PRIMARY KEY, purchase_intent_id UUID NOT NULL REFERENCES public.purchase_intents(purchase_intent_id),
 creator_profile_id BIGINT NOT NULL, fanvue_account_id BIGINT NOT NULL,
 telegram_user_id BIGINT NOT NULL, telegram_chat_id BIGINT NOT NULL,
 nudge_sequence INTEGER NOT NULL CHECK(nudge_sequence>0),
 nudge_reason TEXT NOT NULL CHECK(nudge_reason IN ('CONTEXTUAL','ENGAGEMENT','TIMED')),
 eligible_at TIMESTAMPTZ NOT NULL, authorized_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 operation_id UUID UNIQUE, delivery_state TEXT NOT NULL DEFAULT 'AUTHORIZED'
   CHECK(delivery_state IN ('AUTHORIZED','GENERATED','SENDING','SENT_CONFIRMED','FAILED','SEND_UNCERTAIN','SUPPRESSED')),
 confirmed_at TIMESTAMPTZ, outbound_telegram_message_id BIGINT,
 customer_response_observed_at TIMESTAMPTZ, purchase_observed_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(purchase_intent_id,nudge_sequence),
 CHECK((delivery_state='SENT_CONFIRMED')=(confirmed_at IS NOT NULL AND outbound_telegram_message_id IS NOT NULL))
);
CREATE INDEX active_offer_follow_through_scope_idx ON public.active_offer_follow_through_events
 (creator_profile_id,fanvue_account_id,telegram_user_id,purchase_intent_id,confirmed_at DESC);
