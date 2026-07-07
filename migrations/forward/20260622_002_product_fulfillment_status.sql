BEGIN;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS fulfillment_status TEXT;

UPDATE public.products
SET fulfillment_status = CASE
    WHEN media_link IS NULL OR BTRIM(media_link) = '' THEN 'NOT_READY'
    WHEN LOWER(SPLIT_PART(BTRIM(media_link), ':', 1))
        IN ('http', 'https', 'local')
        THEN 'READY'
    ELSE 'FAILED'
END
WHERE fulfillment_status IS NULL
   OR fulfillment_status = '';

ALTER TABLE public.products
    ALTER COLUMN fulfillment_status SET DEFAULT 'NOT_READY',
    ALTER COLUMN fulfillment_status SET NOT NULL;

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_fulfillment_status_check,
    ADD CONSTRAINT products_fulfillment_status_check CHECK (
        fulfillment_status IN ('NOT_READY', 'READY', 'FAILED')
    );

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_active_catalog_fields_check,
    ADD CONSTRAINT products_active_catalog_fields_check CHECK (
        status <> 'ACTIVE'
        OR (
            price_cents IS NOT NULL
            AND price_cents >= 0
        )
    );

CREATE INDEX IF NOT EXISTS idx_products_fulfillment_status
    ON public.products(fulfillment_status);

COMMIT;
