BEGIN;

CREATE TABLE public.creator_content_publications (
    publication_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    platform TEXT NOT NULL,
    destination TEXT NOT NULL,
    telegram_channel_id BIGINT NOT NULL,
    telegram_message_id BIGINT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    publication_status TEXT NOT NULL CHECK (publication_status = 'PUBLISHED'),
    generated_image_id TEXT NOT NULL,
    published_asset_id BIGINT NULL REFERENCES public.content_items(id) ON DELETE SET NULL,
    caption_result_id TEXT NULL,
    photoshoot_id TEXT NULL,
    generation_lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
    media_identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_caption TEXT NOT NULL DEFAULT '',
    cta_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    provider_identifiers JSONB NOT NULL DEFAULT '{}'::jsonb,
    factual_visual_summary TEXT NULL,
    setting TEXT NULL,
    clothing TEXT NULL,
    pose TEXT NULL,
    activity TEXT NULL,
    expression TEXT NULL,
    useful_objects JSONB NOT NULL DEFAULT '[]'::jsonb,
    mood TEXT NULL,
    themes JSONB NOT NULL DEFAULT '[]'::jsonb,
    safety_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    intelligence_source TEXT NOT NULL,
    intelligence_version TEXT NOT NULL,
    intelligence_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    search_document TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT creator_content_publications_telegram_identity_unique
        UNIQUE (platform, destination, telegram_channel_id, telegram_message_id)
);

CREATE INDEX idx_creator_content_publications_creator
    ON public.creator_content_publications (creator_profile_id, published_at DESC);
CREATE INDEX idx_creator_content_publications_channel
    ON public.creator_content_publications
    (creator_profile_id, platform, destination, telegram_channel_id, published_at DESC);
CREATE INDEX idx_creator_content_publications_message
    ON public.creator_content_publications (telegram_channel_id, telegram_message_id);
CREATE INDEX idx_creator_content_publications_generated_image
    ON public.creator_content_publications (generated_image_id);
CREATE INDEX idx_creator_content_publications_asset
    ON public.creator_content_publications (published_asset_id)
    WHERE published_asset_id IS NOT NULL;
CREATE INDEX idx_creator_content_publications_photoshoot
    ON public.creator_content_publications (photoshoot_id)
    WHERE photoshoot_id IS NOT NULL;
CREATE INDEX idx_creator_content_publications_search
    ON public.creator_content_publications
    USING GIN (to_tsvector('simple', search_document));

COMMIT;
