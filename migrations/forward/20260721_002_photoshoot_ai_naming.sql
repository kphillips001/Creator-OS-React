ALTER TABLE public.photoshoot_commerce_deliverables
    ADD COLUMN IF NOT EXISTS ai_title TEXT NULL,
    ADD COLUMN IF NOT EXISTS ai_description TEXT NULL,
    ADD COLUMN IF NOT EXISTS user_title TEXT NULL,
    ADD COLUMN IF NOT EXISTS user_description TEXT NULL,
    ADD COLUMN IF NOT EXISTS naming_status TEXT NOT NULL DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS naming_error TEXT NULL;

ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_naming_status_check;

ALTER TABLE public.photoshoot_commerce_deliverables
    ADD CONSTRAINT photoshoot_deliverable_naming_status_check
    CHECK (naming_status IN ('PENDING', 'COMPLETE', 'FAILED'));
