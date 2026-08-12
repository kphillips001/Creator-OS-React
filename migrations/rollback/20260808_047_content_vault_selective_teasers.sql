ALTER TABLE public.commercial_teasers
    DROP CONSTRAINT IF EXISTS commercial_teasers_check;

ALTER TABLE public.commercial_teasers
    ADD CONSTRAINT commercial_teasers_check CHECK (
        (distribution_use='CHAT' AND teaser_style='SELECTIVE_BLUR'
            AND derived_asset_id IS NOT NULL AND mask_path IS NOT NULL)
        OR (distribution_use='CONTENT_VAULT' AND teaser_style='FULL_BLUR')
    );
