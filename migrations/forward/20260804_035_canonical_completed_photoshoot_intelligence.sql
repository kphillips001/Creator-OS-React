ALTER TABLE public.photoshoot_intelligence_profiles
    ADD COLUMN IF NOT EXISTS intelligence_version TEXT NOT NULL DEFAULT 'completed_photoshoot_v1',
    ADD COLUMN IF NOT EXISTS pipeline_stage TEXT NOT NULL DEFAULT 'PENDING',
    ADD COLUMN IF NOT EXISTS stage_status JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS production_analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS cross_validation JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS analysis_completed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.photoshoot_shot_intelligence_profiles (
    photoshoot_session_id TEXT NOT NULL,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id),
    intelligence_version TEXT NOT NULL,
    shot_order INTEGER NOT NULL CHECK (shot_order > 0),
    status TEXT NOT NULL,
    sequence_role TEXT,
    profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    production_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (photoshoot_session_id, asset_id, intelligence_version),
    UNIQUE (photoshoot_session_id, intelligence_version, shot_order)
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_shot_intelligence_status
    ON public.photoshoot_shot_intelligence_profiles
    (photoshoot_session_id, intelligence_version, status, shot_order);
