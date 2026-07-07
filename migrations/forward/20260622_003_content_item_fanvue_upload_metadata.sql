BEGIN;

ALTER TABLE public.content_items
    ADD COLUMN IF NOT EXISTS fanvue_upload_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
