CREATE TABLE IF NOT EXISTS public.photoshoot_session_sales_strategies (
    photoshoot_session_id TEXT NOT NULL,
    deliverable_id UUID NOT NULL
        REFERENCES public.photoshoot_commerce_deliverables(deliverable_id) ON DELETE CASCADE,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    strategy_version TEXT NOT NULL,
    intelligence_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('READY','FAILED')),
    strategy_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    model TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (photoshoot_session_id, strategy_version),
    UNIQUE (deliverable_id, strategy_version)
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_session_sales_strategy_latest
    ON public.photoshoot_session_sales_strategies
    (photoshoot_session_id, generated_at DESC, strategy_version DESC)
    WHERE status='READY';
