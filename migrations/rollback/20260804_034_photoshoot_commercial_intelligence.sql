-- Historical AI naming columns remain untouched. Canonical fields are intentionally retained on rollback.
ALTER TABLE public.photoshoot_analysis_workflows
    DROP CONSTRAINT IF EXISTS photoshoot_analysis_stage_check;
ALTER TABLE public.photoshoot_analysis_workflows
    ADD CONSTRAINT photoshoot_analysis_stage_check CHECK (current_stage IN (
        'PENDING','MEMBER_ANALYSIS_PENDING','MEMBER_ANALYSIS_RUNNING','MEMBER_ANALYSIS_FAILED',
        'PHOTOSHOOT_INTELLIGENCE_PENDING','PHOTOSHOOT_INTELLIGENCE_RUNNING','PHOTOSHOOT_INTELLIGENCE_FAILED',
        'NAMING_PENDING','NAMING_RUNNING','NAMING_FAILED','READY'
    ));
