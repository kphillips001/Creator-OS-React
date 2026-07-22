ALTER TABLE public.photoshoot_commerce_deliverables
    DROP CONSTRAINT IF EXISTS photoshoot_deliverable_naming_status_check,
    DROP COLUMN IF EXISTS naming_error,
    DROP COLUMN IF EXISTS naming_status,
    DROP COLUMN IF EXISTS user_description,
    DROP COLUMN IF EXISTS user_title,
    DROP COLUMN IF EXISTS ai_description,
    DROP COLUMN IF EXISTS ai_title;
