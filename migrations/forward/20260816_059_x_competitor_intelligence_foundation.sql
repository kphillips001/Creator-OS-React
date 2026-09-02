BEGIN;

CREATE SCHEMA IF NOT EXISTS x_intelligence;

CREATE TABLE IF NOT EXISTS x_intelligence.competitors (
    id UUID PRIMARY KEY,
    x_user_id TEXT,
    username TEXT NOT NULL,
    display_name TEXT,
    profile_image_url TEXT,
    profile_banner_url TEXT,
    bio TEXT,
    location TEXT,
    account_created_at TIMESTAMPTZ,
    verified BOOLEAN,
    verification_type TEXT,
    tracking_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    watchlisted BOOLEAN NOT NULL DEFAULT FALSE,
    shadow BOOLEAN,
    telegram_channel TEXT,
    telegram_members BIGINT,
    joined DATE,
    allowed_responses TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_x_intelligence_competitors_x_user_id UNIQUE (x_user_id),
    CONSTRAINT ck_x_intelligence_competitors_username_not_blank CHECK (BTRIM(username) <> ''),
    CONSTRAINT ck_x_intelligence_competitors_telegram_members CHECK (telegram_members IS NULL OR telegram_members >= 0)
);

CREATE TABLE IF NOT EXISTS x_intelligence.competitor_profile_snapshots (
    id UUID PRIMARY KEY,
    competitor_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    observation_date DATE NOT NULL,
    followers_count BIGINT NOT NULL,
    following_count BIGINT,
    statuses_count BIGINT,
    media_count BIGINT,
    favorites_count BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_x_intelligence_profile_snapshots_competitor FOREIGN KEY (competitor_id) REFERENCES x_intelligence.competitors(id) ON DELETE CASCADE,
    CONSTRAINT uq_x_intelligence_profile_snapshots_daily UNIQUE (competitor_id, observation_date),
    CONSTRAINT ck_x_intelligence_profile_snapshots_counts CHECK (
        followers_count >= 0 AND
        (following_count IS NULL OR following_count >= 0) AND
        (statuses_count IS NULL OR statuses_count >= 0) AND
        (media_count IS NULL OR media_count >= 0) AND
        (favorites_count IS NULL OR favorites_count >= 0)
    )
);

CREATE TABLE IF NOT EXISTS x_intelligence.competitor_posts (
    id UUID PRIMARY KEY,
    competitor_id UUID NOT NULL,
    x_tweet_id TEXT NOT NULL,
    text TEXT,
    posted_at TIMESTAMPTZ NOT NULL,
    language TEXT,
    conversation_id TEXT,
    is_reply BOOLEAN NOT NULL DEFAULT FALSE,
    is_quote BOOLEAN NOT NULL DEFAULT FALSE,
    is_retweet BOOLEAN NOT NULL DEFAULT FALSE,
    has_media BOOLEAN NOT NULL DEFAULT FALSE,
    media_metadata JSONB NOT NULL DEFAULT '[]'::JSONB,
    like_count BIGINT,
    reply_count BIGINT,
    retweet_count BIGINT,
    quote_count BIGINT,
    view_count BIGINT,
    bookmark_count BIGINT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_x_intelligence_competitor_posts_x_tweet_id UNIQUE (x_tweet_id),
    CONSTRAINT fk_x_intelligence_competitor_posts_competitor FOREIGN KEY (competitor_id) REFERENCES x_intelligence.competitors(id) ON DELETE CASCADE,
    CONSTRAINT ck_x_intelligence_competitor_posts_tweet_id_not_blank CHECK (BTRIM(x_tweet_id) <> ''),
    CONSTRAINT ck_x_intelligence_competitor_posts_media_metadata CHECK (JSONB_TYPEOF(media_metadata) = 'array'),
    CONSTRAINT ck_x_intelligence_competitor_posts_counts CHECK (
        (like_count IS NULL OR like_count >= 0) AND
        (reply_count IS NULL OR reply_count >= 0) AND
        (retweet_count IS NULL OR retweet_count >= 0) AND
        (quote_count IS NULL OR quote_count >= 0) AND
        (view_count IS NULL OR view_count >= 0) AND
        (bookmark_count IS NULL OR bookmark_count >= 0)
    )
);

CREATE TABLE IF NOT EXISTS x_intelligence.competitor_sync_runs (
    id UUID PRIMARY KEY,
    competitor_id UUID NOT NULL,
    sync_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    profile_synced BOOLEAN NOT NULL DEFAULT FALSE,
    posts_synced BOOLEAN NOT NULL DEFAULT FALSE,
    posts_returned INTEGER NOT NULL DEFAULT 0,
    new_posts INTEGER NOT NULL DEFAULT 0,
    existing_posts INTEGER NOT NULL DEFAULT 0,
    provider TEXT,
    provider_requests INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(12, 6),
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_x_intelligence_sync_runs_competitor FOREIGN KEY (competitor_id) REFERENCES x_intelligence.competitors(id) ON DELETE CASCADE,
    CONSTRAINT ck_x_intelligence_sync_runs_type CHECK (sync_type IN ('INITIAL', 'WEEKLY', 'MANUAL')),
    CONSTRAINT ck_x_intelligence_sync_runs_status CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')),
    CONSTRAINT ck_x_intelligence_sync_runs_counts CHECK (posts_returned >= 0 AND new_posts >= 0 AND existing_posts >= 0 AND provider_requests >= 0),
    CONSTRAINT ck_x_intelligence_sync_runs_cost CHECK (estimated_cost IS NULL OR estimated_cost >= 0),
    CONSTRAINT ck_x_intelligence_sync_runs_completion CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at)
);

CREATE INDEX IF NOT EXISTS idx_x_intelligence_competitors_username_lower ON x_intelligence.competitors (LOWER(username));
CREATE INDEX IF NOT EXISTS idx_x_intelligence_competitors_tracking ON x_intelligence.competitors (updated_at DESC) WHERE tracking_enabled;
CREATE INDEX IF NOT EXISTS idx_x_intelligence_competitors_watchlist ON x_intelligence.competitors (updated_at DESC) WHERE watchlisted;
CREATE INDEX IF NOT EXISTS idx_x_intelligence_profile_snapshots_observed ON x_intelligence.competitor_profile_snapshots (competitor_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_x_intelligence_posts_competitor_posted ON x_intelligence.competitor_posts (competitor_id, posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_x_intelligence_sync_runs_competitor_started ON x_intelligence.competitor_sync_runs (competitor_id, started_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_x_intelligence_sync_runs_active ON x_intelligence.competitor_sync_runs (status, created_at) WHERE status IN ('QUEUED', 'RUNNING');

COMMIT;
