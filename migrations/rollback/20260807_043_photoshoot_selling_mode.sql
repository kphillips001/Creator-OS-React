ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_commerce_deliverables_selling_mode_check,
    DROP COLUMN IF EXISTS selling_mode;
