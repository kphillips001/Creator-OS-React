CREATE TABLE IF NOT EXISTS public.asset_lineage_relationships (
    relationship_id UUID NOT NULL,
    source_asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    derived_asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    source_position INTEGER NOT NULL CHECK (source_position >= 0),
    derivation_kind TEXT NOT NULL CHECK (
        derivation_kind IN (
            'IMAGE_TO_VIDEO','IMAGE_TO_GIF','IMAGE_TO_ANIMATION',
            'IMAGE_TO_CINEMAGRAPH','IMAGE_UPSCALE','IMAGE_EDIT',
            'VIDEO_TO_GIF','VIDEO_TO_CLIP','VIDEO_EDIT',
            'MULTI_IMAGE_TO_VIDEO','MULTI_ASSET_COMPOSITION',
            'FORMAT_TRANSFORMATION','OTHER_DERIVED_MEDIA'
        )
    ),
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (relationship_id, source_asset_id),
    UNIQUE (relationship_id, source_position),
    CHECK (source_asset_id <> derived_asset_id)
);

CREATE INDEX IF NOT EXISTS idx_asset_lineage_source
    ON public.asset_lineage_relationships (source_asset_id, derived_asset_id);

CREATE INDEX IF NOT EXISTS idx_asset_lineage_derived
    ON public.asset_lineage_relationships (derived_asset_id, source_asset_id);
