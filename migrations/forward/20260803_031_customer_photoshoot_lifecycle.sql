BEGIN;
CREATE TABLE IF NOT EXISTS public.customer_photoshoot_lifecycles (
 lifecycle_id UUID PRIMARY KEY, creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
 customer_commerce_profile_id UUID NOT NULL REFERENCES public.customer_commerce_profiles(customer_commerce_profile_id) ON DELETE RESTRICT,
 photoshoot_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NEVER_STARTED' CHECK(status IN ('NEVER_STARTED','INTRODUCED','ACTIVE','PAUSED','STALLED','COMPLETED','ABANDONED','DECLINED')),
 current_position INTEGER NOT NULL DEFAULT 0 CHECK(current_position>=0), first_started_at TIMESTAMPTZ, last_activity_at TIMESTAMPTZ, paused_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, abandoned_at TIMESTAMPTZ, revival_eligible_at TIMESTAMPTZ,
 first_sales_session_id UUID REFERENCES public.sales_sessions(sales_session_id) ON DELETE SET NULL, last_sales_session_id UUID REFERENCES public.sales_sessions(sales_session_id) ON DELETE SET NULL,
 last_purchase_intent_id UUID REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE SET NULL, selected_offering_id UUID REFERENCES public.commercial_offerings(offering_id) ON DELETE SET NULL,
 recommendation_reason TEXT, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(creator_profile_id,customer_commerce_profile_id,photoshoot_id));
CREATE TABLE IF NOT EXISTS public.customer_photoshoot_lifecycle_events (
 event_id BIGSERIAL PRIMARY KEY,lifecycle_id UUID NOT NULL REFERENCES public.customer_photoshoot_lifecycles(lifecycle_id) ON DELETE CASCADE,event_type TEXT NOT NULL,previous_status TEXT,new_status TEXT NOT NULL,asset_id BIGINT REFERENCES public.content_items(id) ON DELETE RESTRICT,purchase_outcome_id UUID,sales_session_id UUID REFERENCES public.sales_sessions(sales_session_id) ON DELETE SET NULL,purchase_intent_id UUID REFERENCES public.purchase_intents(purchase_intent_id) ON DELETE SET NULL,metadata JSONB NOT NULL DEFAULT '{}'::jsonb,occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(lifecycle_id,purchase_outcome_id,asset_id));
CREATE TABLE IF NOT EXISTS public.customer_photoshoot_lifecycle_sessions (lifecycle_id UUID NOT NULL REFERENCES public.customer_photoshoot_lifecycles(lifecycle_id) ON DELETE CASCADE,sales_session_id UUID NOT NULL REFERENCES public.sales_sessions(sales_session_id) ON DELETE CASCADE,associated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(lifecycle_id,sales_session_id));
CREATE INDEX IF NOT EXISTS idx_customer_photoshoot_lifecycle_customer ON public.customer_photoshoot_lifecycles(creator_profile_id,customer_commerce_profile_id,status);
COMMIT;
