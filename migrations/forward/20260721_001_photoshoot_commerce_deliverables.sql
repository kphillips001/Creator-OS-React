CREATE TABLE IF NOT EXISTS public.photoshoot_asset_memberships (
    photoshoot_session_id TEXT NOT NULL,
    asset_id BIGINT NOT NULL REFERENCES public.content_items(id),
    shot_order INTEGER NOT NULL CHECK (shot_order > 0),
    approved BOOLEAN NOT NULL DEFAULT TRUE,
    is_hero BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (photoshoot_session_id, asset_id),
    UNIQUE (photoshoot_session_id, shot_order)
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_membership_asset
    ON public.photoshoot_asset_memberships (asset_id) WHERE approved = TRUE;

CREATE TABLE IF NOT EXISTS public.photoshoot_intelligence_profiles (
    photoshoot_session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.photoshoot_commerce_deliverables (
    deliverable_id UUID PRIMARY KEY,
    photoshoot_session_id TEXT NOT NULL UNIQUE,
    creator_profile_id BIGINT NOT NULL,
    deliverable_type TEXT NOT NULL DEFAULT 'photoshoot' CHECK (deliverable_type = 'photoshoot'),
    display_name TEXT NOT NULL,
    ordered_member_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    shot_count INTEGER NOT NULL DEFAULT 0,
    hero_asset_id BIGINT NULL REFERENCES public.content_items(id),
    gallery_path TEXT NULL,
    gallery_manifest_path TEXT NULL,
    completed_at TIMESTAMPTZ NULL,
    intelligence_status TEXT NOT NULL DEFAULT 'PENDING',
    commerce_status TEXT NOT NULL DEFAULT 'ANALYZING',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    archived_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photoshoot_deliverables_active
    ON public.photoshoot_commerce_deliverables (creator_profile_id, is_active, is_archived);
