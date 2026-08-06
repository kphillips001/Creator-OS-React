DROP TABLE IF EXISTS public.photoshoot_shot_intelligence_profiles;
ALTER TABLE public.photoshoot_intelligence_profiles
    DROP COLUMN IF EXISTS intelligence_version,
    DROP COLUMN IF EXISTS pipeline_stage,
    DROP COLUMN IF EXISTS stage_status,
    DROP COLUMN IF EXISTS production_analysis,
    DROP COLUMN IF EXISTS cross_validation,
    DROP COLUMN IF EXISTS analysis_completed_at;
