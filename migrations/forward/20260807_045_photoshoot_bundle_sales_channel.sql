ALTER TABLE public.photoshoot_commerce_deliverables
    ADD COLUMN IF NOT EXISTS bundle_sales_channel TEXT;

UPDATE public.photoshoot_commerce_deliverables
SET bundle_sales_channel = 'CHAT'
WHERE selling_mode = 'BUNDLE'
  AND bundle_sales_channel IS NULL;

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_commerce_deliverables_bundle_sales_channel_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_commerce_deliverables_bundle_sales_channel_check
    CHECK (bundle_sales_channel IS NULL OR bundle_sales_channel IN ('CHAT', 'CONTENT_WALL'));
