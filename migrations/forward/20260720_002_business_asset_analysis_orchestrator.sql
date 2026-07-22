ALTER TABLE public.asset_intelligence_profiles
    DROP CONSTRAINT IF EXISTS asset_intelligence_profiles_analysis_status_check;

ALTER TABLE public.asset_intelligence_profiles
    ADD CONSTRAINT asset_intelligence_profiles_analysis_status_check CHECK (
        analysis_status IN (
            'REGISTERED','PENDING',
            'NUDENET_PENDING','NUDENET_RUNNING','NUDENET_COMPLETE','NUDENET_FAILED',
            'VISION_PENDING','VISION_RUNNING','VISION_COMPLETE','VISION_FAILED',
            'GROK_PENDING','GROK_RUNNING','GROK_COMPLETE','GROK_FAILED',
            'CONTENT_INTELLIGENCE_PENDING','CONTENT_INTELLIGENCE_RUNNING',
            'CONTENT_INTELLIGENCE_COMPLETE','CONTENT_INTELLIGENCE_FAILED',
            'ANALYZING','READY','PARTIAL','FAILED'
        )
    );
