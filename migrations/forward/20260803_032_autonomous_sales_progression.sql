BEGIN;
ALTER TABLE public.commercial_role_assignments DROP CONSTRAINT IF EXISTS commercial_role_assignments_role_check;
ALTER TABLE public.commercial_role_assignments ADD CONSTRAINT commercial_role_assignments_role_check CHECK(role IN ('DISCOVERY','TEASER','HERO','CORE','CORE_SESSION','PROGRESSION','PREMIUM','FINALE','FINALE_IMAGE','FINALE_VIDEO','BONUS'));
ALTER TABLE public.commercial_role_history DROP CONSTRAINT IF EXISTS commercial_role_history_role_check;
ALTER TABLE public.commercial_role_history ADD CONSTRAINT commercial_role_history_role_check CHECK(role IN ('DISCOVERY','TEASER','HERO','CORE','CORE_SESSION','PROGRESSION','PREMIUM','FINALE','FINALE_IMAGE','FINALE_VIDEO','BONUS'));
CREATE TABLE IF NOT EXISTS public.autonomous_sales_actions(action_id UUID PRIMARY KEY,creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,customer_commerce_profile_id UUID NOT NULL REFERENCES public.customer_commerce_profiles(customer_commerce_profile_id) ON DELETE RESTRICT,lifecycle_id UUID REFERENCES public.customer_photoshoot_lifecycles(lifecycle_id) ON DELETE SET NULL,action TEXT NOT NULL,action_fingerprint TEXT NOT NULL,decision JSONB NOT NULL,expires_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(customer_commerce_profile_id,action_fingerprint));
ALTER TABLE public.commercial_role_assignments ALTER COLUMN vocabulary_version SET DEFAULT '2.0';
CREATE INDEX IF NOT EXISTS idx_autonomous_sales_actions_customer ON public.autonomous_sales_actions(creator_profile_id,customer_commerce_profile_id,created_at DESC);
COMMIT;
