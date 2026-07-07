BEGIN;

ALTER TABLE public.products
    RENAME COLUMN sku TO internal_name;
ALTER TABLE public.products
    RENAME COLUMN title TO display_name;
ALTER TABLE public.products
    RENAME COLUMN base_price_minor TO price_cents;

ALTER TABLE public.products
    ADD COLUMN media_link TEXT NULL,
    ADD COLUMN tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN themes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_status_check;

UPDATE public.products
SET status = CASE status
    WHEN 'draft' THEN 'DRAFT'
    WHEN 'active' THEN 'ACTIVE'
    WHEN 'retired' THEN 'DISABLED'
    WHEN 'archived' THEN 'ARCHIVED'
    ELSE UPPER(status)
END;

ALTER TABLE public.products
    ADD CONSTRAINT products_catalog_status_check CHECK (
        status IN ('DRAFT', 'ACTIVE', 'DISABLED', 'ARCHIVED')
    ),
    ADD CONSTRAINT products_internal_name_not_blank CHECK (
        BTRIM(internal_name) <> ''
    ),
    ADD CONSTRAINT products_display_name_not_blank CHECK (
        BTRIM(display_name) <> ''
    ),
    ADD CONSTRAINT products_currency_format_check CHECK (
        currency = UPPER(currency) AND BTRIM(currency) ~ '^[A-Z]{3}$'
    ),
    ADD CONSTRAINT products_active_catalog_fields_check CHECK (
        status <> 'ACTIVE'
        OR (
            price_cents IS NOT NULL
            AND price_cents >= 0
            AND media_link IS NOT NULL
            AND BTRIM(media_link) <> ''
        )
    );

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_supersedes_product_id_fkey,
    DROP COLUMN IF EXISTS supersedes_product_id;

CREATE INDEX IF NOT EXISTS idx_products_catalog_creator_status
    ON public.products(creator_profile_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_products_catalog_tags
    ON public.products USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_products_catalog_themes
    ON public.products USING GIN(themes);

COMMIT;
