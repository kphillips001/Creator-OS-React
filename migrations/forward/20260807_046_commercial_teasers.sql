CREATE TABLE IF NOT EXISTS public.commercial_teasers (
    teaser_id UUID PRIMARY KEY,
    creator_profile_id INTEGER NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    source_asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    derived_asset_id BIGINT REFERENCES public.content_items(id) ON DELETE RESTRICT,
    derivative_path TEXT NOT NULL,
    teaser_style TEXT NOT NULL CHECK (teaser_style IN ('FULL_BLUR','SELECTIVE_BLUR')),
    distribution_use TEXT NOT NULL CHECK (distribution_use IN ('CHAT','CONTENT_VAULT')),
    mask_path TEXT,
    mask_width INTEGER CHECK (mask_width BETWEEN 1 AND 2048),
    mask_height INTEGER CHECK (mask_height BETWEEN 1 AND 2048),
    mask_version TEXT,
    blur_strength INTEGER CHECK (blur_strength BETWEEN 1 AND 80),
    status TEXT NOT NULL DEFAULT 'READY' CHECK (status IN ('READY','NEEDS_ATTENTION')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_asset_id, distribution_use),
    CHECK (
      (distribution_use='CHAT' AND teaser_style='SELECTIVE_BLUR' AND derived_asset_id IS NOT NULL AND mask_path IS NOT NULL)
      OR (distribution_use='CONTENT_VAULT' AND teaser_style='FULL_BLUR')
    )
);

CREATE INDEX IF NOT EXISTS idx_commercial_teasers_creator
    ON public.commercial_teasers(creator_profile_id, source_asset_id);
