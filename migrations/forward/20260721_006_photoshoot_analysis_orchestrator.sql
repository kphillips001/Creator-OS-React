CREATE TABLE IF NOT EXISTS public.photoshoot_analysis_workflows (
    deliverable_id UUID PRIMARY KEY REFERENCES public.photoshoot_commerce_deliverables(deliverable_id),
    current_stage TEXT NOT NULL DEFAULT 'PENDING',
    worker_id TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    failed_member_asset_id BIGINT NULL REFERENCES public.content_items(id),
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT photoshoot_analysis_stage_check CHECK (current_stage IN (
        'PENDING','MEMBER_ANALYSIS_PENDING','MEMBER_ANALYSIS_RUNNING','MEMBER_ANALYSIS_FAILED',
        'PHOTOSHOOT_INTELLIGENCE_PENDING','PHOTOSHOOT_INTELLIGENCE_RUNNING','PHOTOSHOOT_INTELLIGENCE_FAILED',
        'NAMING_PENDING','NAMING_RUNNING','NAMING_FAILED','READY'
    ))
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_analysis_claim
    ON public.photoshoot_analysis_workflows (current_stage, lease_expires_at, updated_at);

INSERT INTO public.photoshoot_analysis_workflows (deliverable_id,current_stage)
SELECT deliverable_id,'PENDING'
FROM public.photoshoot_commerce_deliverables
WHERE registration_state='REGISTERED' AND is_archived=FALSE
ON CONFLICT (deliverable_id) DO NOTHING;

UPDATE public.photoshoot_commerce_deliverables d
SET intelligence_status='PENDING',commerce_status='ANALYZING',updated_at=now()
WHERE d.registration_state='REGISTERED' AND d.is_archived=FALSE
  AND EXISTS (SELECT 1 FROM public.photoshoot_analysis_workflows w
              WHERE w.deliverable_id=d.deliverable_id AND w.current_stage<>'READY');
