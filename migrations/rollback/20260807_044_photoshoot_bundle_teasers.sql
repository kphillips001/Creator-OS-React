DROP TABLE IF EXISTS public.photoshoot_bundle_teasers;
DELETE FROM public.asset_lineage_relationships WHERE derivation_kind='SELECTIVE_BLUR';
ALTER TABLE public.asset_lineage_relationships
    DROP CONSTRAINT IF EXISTS asset_lineage_relationships_derivation_kind_check;
ALTER TABLE public.asset_lineage_relationships
    ADD CONSTRAINT asset_lineage_relationships_derivation_kind_check CHECK (
        derivation_kind IN (
            'IMAGE_TO_VIDEO','IMAGE_TO_GIF','IMAGE_TO_ANIMATION','IMAGE_TO_CINEMAGRAPH',
            'IMAGE_UPSCALE','IMAGE_EDIT','VIDEO_TO_GIF','VIDEO_TO_CLIP','VIDEO_EDIT',
            'MULTI_IMAGE_TO_VIDEO','MULTI_ASSET_COMPOSITION','FORMAT_TRANSFORMATION',
            'OTHER_DERIVED_MEDIA'
        )
    );
