ALTER TABLE public.asset_lineage_relationships
    DROP CONSTRAINT IF EXISTS asset_lineage_relationships_derivation_kind_check;

ALTER TABLE public.asset_lineage_relationships
    ADD CONSTRAINT asset_lineage_relationships_derivation_kind_check CHECK (
        derivation_kind IN (
            'IMAGE_TO_VIDEO','IMAGE_TO_GIF','IMAGE_TO_ANIMATION','IMAGE_TO_CINEMAGRAPH',
            'IMAGE_UPSCALE','IMAGE_EDIT','SELECTIVE_BLUR','VIDEO_TO_GIF','VIDEO_TO_CLIP',
            'VIDEO_EDIT','MULTI_IMAGE_TO_VIDEO','MULTI_ASSET_COMPOSITION',
            'FORMAT_TRANSFORMATION','OTHER_DERIVED_MEDIA'
        )
    );

CREATE TABLE IF NOT EXISTS public.photoshoot_bundle_teasers (
    deliverable_id UUID PRIMARY KEY
        REFERENCES public.photoshoot_commerce_deliverables(deliverable_id) ON DELETE CASCADE,
    creator_profile_id INTEGER NOT NULL REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    source_asset_id BIGINT NOT NULL REFERENCES public.content_items(id) ON DELETE RESTRICT,
    teaser_asset_id BIGINT NOT NULL UNIQUE REFERENCES public.content_items(id) ON DELETE RESTRICT,
    commercial_role TEXT NOT NULL DEFAULT 'BUNDLE_PROMOTIONAL_TEASER'
        CHECK (commercial_role='BUNDLE_PROMOTIONAL_TEASER'),
    mask_path TEXT NOT NULL,
    mask_width INTEGER NOT NULL CHECK (mask_width BETWEEN 1 AND 2048),
    mask_height INTEGER NOT NULL CHECK (mask_height BETWEEN 1 AND 2048),
    mask_version TEXT NOT NULL DEFAULT 'selective_blur_mask_v1',
    blur_strength INTEGER NOT NULL CHECK (blur_strength BETWEEN 1 AND 80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_bundle_teasers_source
    ON public.photoshoot_bundle_teasers(source_asset_id);
