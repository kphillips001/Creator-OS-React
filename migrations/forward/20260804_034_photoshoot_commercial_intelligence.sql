-- Canonical Commercial Intelligence replaces the standalone Photoshoot naming projection.
ALTER TABLE public.photoshoot_intelligence_profiles
    ADD COLUMN IF NOT EXISTS commercial_title TEXT,
    ADD COLUMN IF NOT EXISTS subtitle TEXT,
    ADD COLUMN IF NOT EXISTS commercial_summary TEXT,
    ADD COLUMN IF NOT EXISTS story TEXT,
    ADD COLUMN IF NOT EXISTS theme TEXT,
    ADD COLUMN IF NOT EXISTS experience TEXT,
    ADD COLUMN IF NOT EXISTS emotional_journey TEXT,
    ADD COLUMN IF NOT EXISTS buyer_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS sales_strategy JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS sales_brain_brief TEXT,
    ADD COLUMN IF NOT EXISTS input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS model TEXT,
    ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS generation_status TEXT NOT NULL DEFAULT 'PENDING';

-- Preserve historical copy inside the canonical record so old Gallery pages remain readable.
-- PENDING explicitly marks these rows as safe regeneration candidates; no history is deleted.
UPDATE public.photoshoot_intelligence_profiles intelligence
SET commercial_title=COALESCE(intelligence.commercial_title, deliverable.ai_title),
    commercial_summary=COALESCE(intelligence.commercial_summary, deliverable.ai_description),
    generation_status=CASE
        WHEN intelligence.generated_at IS NOT NULL THEN intelligence.generation_status
        ELSE 'PENDING'
    END,
    updated_at=now()
FROM public.photoshoot_commerce_deliverables deliverable
WHERE deliverable.photoshoot_session_id=intelligence.photoshoot_session_id
  AND (intelligence.commercial_title IS NULL OR intelligence.commercial_summary IS NULL);

ALTER TABLE public.photoshoot_analysis_workflows
    DROP CONSTRAINT IF EXISTS photoshoot_analysis_stage_check;

UPDATE public.photoshoot_analysis_workflows
SET current_stage='PHOTOSHOOT_INTELLIGENCE_PENDING', updated_at=now()
WHERE current_stage IN ('NAMING_PENDING','NAMING_RUNNING','NAMING_FAILED');

ALTER TABLE public.photoshoot_analysis_workflows
    ADD CONSTRAINT photoshoot_analysis_stage_check CHECK (current_stage IN (
        'PENDING','MEMBER_ANALYSIS_PENDING','MEMBER_ANALYSIS_RUNNING','MEMBER_ANALYSIS_FAILED',
        'PHOTOSHOOT_INTELLIGENCE_PENDING','PHOTOSHOOT_INTELLIGENCE_RUNNING',
        'PHOTOSHOOT_INTELLIGENCE_FAILED','READY'
    ));

CREATE UNIQUE INDEX IF NOT EXISTS uq_photoshoot_commercial_intelligence
    ON public.photoshoot_intelligence_profiles (photoshoot_session_id);
