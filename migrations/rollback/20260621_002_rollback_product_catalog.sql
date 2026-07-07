BEGIN;

DROP INDEX IF EXISTS public.idx_products_catalog_themes;
DROP INDEX IF EXISTS public.idx_products_catalog_tags;
DROP INDEX IF EXISTS public.idx_products_catalog_creator_status;

ALTER TABLE public.products
    ADD COLUMN supersedes_product_id UUID NULL;
ALTER TABLE public.products
    ADD CONSTRAINT products_supersedes_product_id_fkey
        FOREIGN KEY (supersedes_product_id)
        REFERENCES public.products(id) ON DELETE SET NULL;

ALTER TABLE public.products
    DROP CONSTRAINT IF EXISTS products_active_catalog_fields_check,
    DROP CONSTRAINT IF EXISTS products_currency_format_check,
    DROP CONSTRAINT IF EXISTS products_display_name_not_blank,
    DROP CONSTRAINT IF EXISTS products_internal_name_not_blank,
    DROP CONSTRAINT IF EXISTS products_catalog_status_check;

UPDATE public.products
SET status = CASE status
    WHEN 'DRAFT' THEN 'draft'
    WHEN 'ACTIVE' THEN 'active'
    WHEN 'DISABLED' THEN 'retired'
    WHEN 'ARCHIVED' THEN 'archived'
    ELSE LOWER(status)
END;

ALTER TABLE public.products
    ADD CONSTRAINT products_status_check CHECK (
        status IN ('draft', 'active', 'retired', 'archived')
    );

ALTER TABLE public.products
    DROP COLUMN IF EXISTS themes,
    DROP COLUMN IF EXISTS tags,
    DROP COLUMN IF EXISTS media_link;

ALTER TABLE public.products
    RENAME COLUMN price_cents TO base_price_minor;
ALTER TABLE public.products
    RENAME COLUMN display_name TO title;
ALTER TABLE public.products
    RENAME COLUMN internal_name TO sku;

COMMIT;
