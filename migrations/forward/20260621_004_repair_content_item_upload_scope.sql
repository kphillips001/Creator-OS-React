BEGIN;

ALTER TABLE public.content_items
    ADD COLUMN IF NOT EXISTS content_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS fanvue_account_id BIGINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'content_items_fanvue_account_id_fkey'
    ) THEN
        ALTER TABLE public.content_items
            ADD CONSTRAINT content_items_fanvue_account_id_fkey
            FOREIGN KEY (fanvue_account_id)
            REFERENCES public.fanvue_accounts(id)
            ON DELETE SET NULL;
    END IF;
END $$;

UPDATE public.content_items
SET content_type = CASE
    WHEN upload_intent LIKE 'teaser_%' THEN 'teaser'
    WHEN upload_intent LIKE 'wall_%' THEN 'wall'
    WHEN upload_intent LIKE 'ppv_%' THEN 'ppv'
    ELSE content_type
END
WHERE content_type IS NULL
  AND upload_intent IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_content_items_fanvue_account_status
    ON public.content_items(fanvue_account_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_items_content_type
    ON public.content_items(content_type);

COMMIT;
