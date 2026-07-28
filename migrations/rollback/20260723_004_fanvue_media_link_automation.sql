DROP TABLE IF EXISTS public.commercial_publication_uploads;
ALTER TABLE public.commercial_publications
 DROP COLUMN IF EXISTS execution_claim_token,
 DROP COLUMN IF EXISTS execution_lease_expires_at;
ALTER TABLE public.commercial_offerings
 DROP CONSTRAINT IF EXISTS commercial_offerings_price_check,
 DROP CONSTRAINT IF EXISTS commercial_offerings_currency_check,
 DROP COLUMN IF EXISTS price_minor,
 DROP COLUMN IF EXISTS currency;
