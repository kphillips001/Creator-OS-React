BEGIN;
DROP TABLE IF EXISTS public.verified_external_customer_identity_audit;
DROP TABLE IF EXISTS public.verified_external_customer_identities;
DROP TABLE IF EXISTS public.canonical_customer_materialization_audit;
DROP TABLE IF EXISTS public.external_customer_identity_observations;
COMMIT;
