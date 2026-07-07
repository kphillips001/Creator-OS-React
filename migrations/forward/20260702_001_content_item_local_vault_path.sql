BEGIN;

ALTER TABLE public.content_items
    ADD COLUMN IF NOT EXISTS local_vault_path TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_content_items_local_vault_path
    ON public.content_items(local_vault_path);

COMMIT;
