ALTER TABLE public.photoshoot_commerce_deliverables
    ADD COLUMN IF NOT EXISTS selling_mode TEXT;

UPDATE public.photoshoot_commerce_deliverables
SET selling_mode = 'SESSION'
WHERE selling_mode IS NULL;

ALTER TABLE public.photoshoot_commerce_deliverables
    ALTER COLUMN selling_mode SET DEFAULT 'SESSION',
    ALTER COLUMN selling_mode SET NOT NULL,
    DROP CONSTRAINT IF EXISTS photoshoot_commerce_deliverables_selling_mode_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_commerce_deliverables_selling_mode_check
    CHECK (selling_mode IN ('SESSION', 'BUNDLE'));
