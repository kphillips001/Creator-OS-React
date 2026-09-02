BEGIN;

CREATE SCHEMA IF NOT EXISTS ig_intelligence;

CREATE TABLE IF NOT EXISTS ig_intelligence.competitors (
    id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    followers_count BIGINT NOT NULL DEFAULT 0,
    profile_image_url TEXT,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ig_competitors_username CHECK (BTRIM(username) <> '' AND username = LOWER(username) AND username NOT LIKE '@%'),
    CONSTRAINT ck_ig_competitors_display_name CHECK (BTRIM(display_name) <> ''),
    CONSTRAINT ck_ig_competitors_followers CHECK (followers_count >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ig_competitors_creator_username
    ON ig_intelligence.competitors (creator_profile_id, LOWER(username));
CREATE INDEX IF NOT EXISTS idx_ig_competitors_active
    ON ig_intelligence.competitors (creator_profile_id, created_at DESC, id)
    WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_ig_competitors_archived
    ON ig_intelligence.competitors (creator_profile_id, archived_at DESC, id)
    WHERE archived_at IS NOT NULL;

COMMIT;
