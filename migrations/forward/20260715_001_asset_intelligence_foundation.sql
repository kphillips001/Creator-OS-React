CREATE TABLE IF NOT EXISTS public.asset_intelligence_profiles (
    asset_id BIGINT PRIMARY KEY
        REFERENCES public.content_items(id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    schema_version TEXT NOT NULL,
    analysis_status TEXT NOT NULL
        CHECK (analysis_status IN ('PENDING', 'ANALYZING', 'READY', 'PARTIAL', 'FAILED')),
    analyzed_at TIMESTAMPTZ,
    profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_profiles_creator
    ON public.asset_intelligence_profiles (creator_profile_id);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_profiles_status
    ON public.asset_intelligence_profiles (analysis_status);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_profiles_data
    ON public.asset_intelligence_profiles USING GIN (profile_data);

CREATE TABLE IF NOT EXISTS public.asset_intelligence_provider_results (
    result_id TEXT PRIMARY KEY,
    asset_id BIGINT NOT NULL
        REFERENCES public.asset_intelligence_profiles(asset_id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL,
    provider_version TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'ANALYZING', 'READY', 'PARTIAL', 'FAILED')),
    analyzed_at TIMESTAMPTZ,
    raw_response JSONB NOT NULL,
    normalized_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    field_confidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_results_asset
    ON public.asset_intelligence_provider_results (asset_id, created_at);

CREATE INDEX IF NOT EXISTS idx_asset_intelligence_results_provider
    ON public.asset_intelligence_provider_results (provider, status);
