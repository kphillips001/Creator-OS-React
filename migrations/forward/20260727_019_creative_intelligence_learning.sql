CREATE TABLE IF NOT EXISTS public.creative_intelligence_profiles (
    id BIGSERIAL PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL UNIQUE
        REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    fanvue_account_id TEXT NOT NULL UNIQUE,
    positive_event_count INTEGER NOT NULL DEFAULT 0,
    negative_event_count INTEGER NOT NULL DEFAULT 0,
    analyzed_image_count INTEGER NOT NULL DEFAULT 0,
    learned_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.creative_intelligence_profiles IS
    'Collection-only creator editorial memory; never consumed by generation in Phase 1.';

CREATE TABLE IF NOT EXISTS public.creative_intelligence_events (
    id BIGSERIAL PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    creator_profile_id INTEGER NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    fanvue_account_id TEXT NOT NULL,
    source_image_id TEXT,
    source_asset_id BIGINT,
    image_reference TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_workflow TEXT NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('positive', 'negative')),
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    analysis_status TEXT NOT NULL
        CHECK (analysis_status IN ('completed', 'failed', 'not_required')),
    analysis_provider TEXT,
    analysis_error TEXT,
    operational_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_creative_intelligence_events_creator
    ON public.creative_intelligence_events (creator_profile_id, created_at);

INSERT INTO public.creative_intelligence_profiles (
    creator_profile_id, fanvue_account_id
)
SELECT id, fanvue_account_id
FROM public.creator_profiles
ON CONFLICT (creator_profile_id) DO NOTHING;
