CREATE TABLE IF NOT EXISTS public.content_intelligence_profiles (
    asset_id BIGINT PRIMARY KEY REFERENCES public.content_items(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    required_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    completed_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    retry_count INTEGER NOT NULL DEFAULT 0,
    source_workflow TEXT,
    approval_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    content_profile JSONB NOT NULL DEFAULT '{}'::jsonb,
    normalized_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_document TEXT,
    error_code TEXT,
    error_message TEXT,
    reanalysis_reason TEXT,
    analysis_started_at TIMESTAMPTZ,
    analysis_completed_at TIMESTAMPTZ,
    last_successful_analysis_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_intelligence_profiles_status
    ON public.content_intelligence_profiles (status);

CREATE INDEX IF NOT EXISTS idx_content_intelligence_profiles_source_workflow
    ON public.content_intelligence_profiles (source_workflow);

CREATE INDEX IF NOT EXISTS idx_content_intelligence_profiles_context
    ON public.content_intelligence_profiles USING GIN (normalized_context);

CREATE INDEX IF NOT EXISTS idx_content_intelligence_profiles_search
    ON public.content_intelligence_profiles USING GIN (to_tsvector('simple', COALESCE(search_document, '')));
