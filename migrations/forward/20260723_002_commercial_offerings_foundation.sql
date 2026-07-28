CREATE TABLE IF NOT EXISTS public.commercial_offerings (
    offering_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL
        REFERENCES public.creator_profiles(id) ON DELETE RESTRICT,
    offering_type TEXT NOT NULL CHECK (
        offering_type IN ('SINGLE_IMAGE','PHOTOSET','VIDEO','STORY','STORY_SET','BUNDLE')
    ),
    title TEXT NOT NULL CHECK (BTRIM(title) <> ''),
    description TEXT NULL,
    hero_asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    primary_sales_channel TEXT NOT NULL CHECK (
        primary_sales_channel IN ('AI_CHAT','TELEGRAM_WALL')
    ),
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (
        status IN ('DRAFT','READY','ARCHIVED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.commercial_offering_assets (
    offering_id UUID NOT NULL
        REFERENCES public.commercial_offerings(offering_id) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL
        REFERENCES public.content_items(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK (position > 0),
    is_hero BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (offering_id, asset_id),
    UNIQUE (offering_id, position)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_commercial_offering_single_hero
    ON public.commercial_offering_assets (offering_id) WHERE is_hero=TRUE;
CREATE INDEX IF NOT EXISTS idx_commercial_offerings_creator_created
    ON public.commercial_offerings (creator_profile_id, created_at DESC, offering_id);
CREATE INDEX IF NOT EXISTS idx_commercial_offerings_creator_type
    ON public.commercial_offerings (creator_profile_id, offering_type);
CREATE INDEX IF NOT EXISTS idx_commercial_offering_assets_asset
    ON public.commercial_offering_assets (asset_id);
