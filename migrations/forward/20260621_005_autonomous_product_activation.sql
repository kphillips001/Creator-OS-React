BEGIN;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS base_price_cents INTEGER NULL
        CHECK (base_price_cents IS NULL OR base_price_cents >= 0),
    ADD COLUMN IF NOT EXISTS min_price_cents INTEGER NULL
        CHECK (min_price_cents IS NULL OR min_price_cents >= 0),
    ADD COLUMN IF NOT EXISTS max_price_cents INTEGER NULL
        CHECK (max_price_cents IS NULL OR max_price_cents >= 0),
    ADD COLUMN IF NOT EXISTS activation_source TEXT NULL,
    ADD COLUMN IF NOT EXISTS activation_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ NULL;

UPDATE public.products
SET base_price_cents = price_cents
WHERE base_price_cents IS NULL
  AND price_cents IS NOT NULL;

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_price_band_check;

ALTER TABLE public.products
    ADD CONSTRAINT products_price_band_check CHECK (
        (
            base_price_cents IS NULL
            AND min_price_cents IS NULL
            AND max_price_cents IS NULL
        )
        OR (
            base_price_cents IS NOT NULL
            AND min_price_cents IS NOT NULL
            AND max_price_cents IS NOT NULL
            AND min_price_cents <= base_price_cents
            AND base_price_cents <= max_price_cents
        )
    );

CREATE INDEX IF NOT EXISTS idx_products_activation_source
    ON public.products(activation_source, activated_at DESC);

COMMIT;
