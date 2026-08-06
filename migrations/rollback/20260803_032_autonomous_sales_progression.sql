BEGIN;
DROP TABLE IF EXISTS public.autonomous_sales_actions;
ALTER TABLE public.commercial_role_assignments ALTER COLUMN vocabulary_version SET DEFAULT '1.0';
ALTER TABLE public.commercial_role_assignments DROP CONSTRAINT IF EXISTS commercial_role_assignments_role_check;
ALTER TABLE public.commercial_role_assignments ADD CONSTRAINT commercial_role_assignments_role_check CHECK(role IN ('DISCOVERY','HERO','CORE','PROGRESSION','PREMIUM','FINALE','BONUS'));
ALTER TABLE public.commercial_role_history DROP CONSTRAINT IF EXISTS commercial_role_history_role_check;
ALTER TABLE public.commercial_role_history ADD CONSTRAINT commercial_role_history_role_check CHECK(role IN ('DISCOVERY','HERO','CORE','PROGRESSION','PREMIUM','FINALE','BONUS'));
COMMIT;
