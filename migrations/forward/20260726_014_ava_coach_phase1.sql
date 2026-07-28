CREATE TABLE IF NOT EXISTS public.ava_personality_versions (
    version_id UUID PRIMARY KEY,
    version_label TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('BASELINE','TARGET','RETIRED')),
    parent_version_id UUID REFERENCES public.ava_personality_versions(version_id),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.ava_coach_snapshots (
    snapshot_id UUID PRIMARY KEY,
    fanvue_account_id BIGINT NOT NULL,
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    overview JSONB NOT NULL,
    evidence_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ava_coach_snapshots_account_created_idx
    ON public.ava_coach_snapshots(fanvue_account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.ava_conversation_insights (
    insight_id UUID PRIMARY KEY,
    snapshot_id UUID NOT NULL REFERENCES public.ava_coach_snapshots(snapshot_id),
    fanvue_account_id BIGINT NOT NULL,
    insight_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence JSONB NOT NULL,
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ava_conversation_insights_snapshot_idx
    ON public.ava_conversation_insights(snapshot_id);

CREATE TABLE IF NOT EXISTS public.ava_coaching_recommendations (
    recommendation_id UUID PRIMARY KEY,
    fanvue_account_id BIGINT NOT NULL,
    recommendation_key TEXT NOT NULL,
    target_version_id UUID NOT NULL REFERENCES public.ava_personality_versions(version_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence JSONB NOT NULL,
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    expected_impact TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'PENDING','APPROVED','REJECTED','DISMISSED','APPLIED'
    )),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(fanvue_account_id, recommendation_key, target_version_id)
);

CREATE TABLE IF NOT EXISTS public.ava_applied_improvements (
    improvement_id UUID PRIMARY KEY,
    recommendation_id UUID NOT NULL UNIQUE
        REFERENCES public.ava_coaching_recommendations(recommendation_id),
    version_id UUID NOT NULL REFERENCES public.ava_personality_versions(version_id),
    evidence JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'APPLIED' CHECK (status='APPLIED'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.ava_personality_versions(
    version_id,version_label,status,notes
) VALUES(
    gen_random_uuid(),'Ava v1.0','BASELINE',
    'Observed production baseline. Phase 1 does not modify runtime behavior.'
) ON CONFLICT(version_label) DO NOTHING;

INSERT INTO public.ava_personality_versions(
    version_id,version_label,status,parent_version_id,notes
)
SELECT gen_random_uuid(),'Ava v1.1','TARGET',version_id,
       'Operator-approved coaching target. Not activated by Phase 1.'
FROM public.ava_personality_versions
WHERE version_label='Ava v1.0'
ON CONFLICT(version_label) DO NOTHING;
