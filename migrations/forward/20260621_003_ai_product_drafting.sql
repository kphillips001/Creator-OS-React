BEGIN;

ALTER TABLE public.content_items
    ADD COLUMN IF NOT EXISTS short_safe_summary TEXT NULL,
    ADD COLUMN IF NOT EXISTS risk_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS analysis_reasoning TEXT NULL,
    ADD COLUMN IF NOT EXISTS analysis_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS media_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS creator_profile_id INTEGER NULL,
    ADD COLUMN IF NOT EXISTS gpt_vision_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS nudenet_result JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS classification_result JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'content_items_creator_profile_id_fkey'
    ) THEN
        ALTER TABLE public.content_items
            ADD CONSTRAINT content_items_creator_profile_id_fkey
            FOREIGN KEY (creator_profile_id)
            REFERENCES public.creator_profiles(id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_content_items_creator_profile_status
    ON public.content_items(creator_profile_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_items_risk_flags
    ON public.content_items USING GIN(risk_flags);

CREATE INDEX IF NOT EXISTS idx_content_items_analysis_provenance
    ON public.content_items USING GIN(analysis_provenance);

COMMIT;
