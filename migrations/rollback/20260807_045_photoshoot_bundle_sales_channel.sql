ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_commerce_deliverables_bundle_sales_channel_check,
    DROP COLUMN IF EXISTS bundle_sales_channel;
