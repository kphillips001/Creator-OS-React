BEGIN;

CREATE TABLE x_intelligence.audience_users (
    id UUID PRIMARY KEY,
    x_user_id TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL,
    display_name TEXT,
    profile_image_url TEXT,
    followers_count BIGINT,
    following_count BIGINT,
    verified BOOLEAN,
    account_created_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_x_audience_users_identity CHECK (BTRIM(x_user_id) <> '' AND BTRIM(username) <> ''),
    CONSTRAINT ck_x_audience_users_counts CHECK ((followers_count IS NULL OR followers_count >= 0) AND (following_count IS NULL OR following_count >= 0))
);

CREATE TABLE x_intelligence.audience_collection_runs (
    id UUID PRIMARY KEY,
    competitor_id UUID NOT NULL REFERENCES x_intelligence.competitors(id) ON DELETE CASCADE,
    window_started_at TIMESTAMPTZ NOT NULL,
    window_ended_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','PARTIAL','SUCCEEDED','FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    posts_considered INTEGER NOT NULL DEFAULT 0,
    posts_processed INTEGER NOT NULL DEFAULT 0,
    reply_records_returned INTEGER NOT NULL DEFAULT 0,
    retweeter_records_returned INTEGER NOT NULL DEFAULT 0,
    quote_records_returned INTEGER NOT NULL DEFAULT 0,
    unique_users_observed INTEGER NOT NULL DEFAULT 0,
    new_users INTEGER NOT NULL DEFAULT 0,
    existing_users INTEGER NOT NULL DEFAULT 0,
    new_signals INTEGER NOT NULL DEFAULT 0,
    existing_signals INTEGER NOT NULL DEFAULT 0,
    provider_requests INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_x_audience_run_window CHECK (window_ended_at >= window_started_at),
    CONSTRAINT ck_x_audience_run_counts CHECK (posts_considered>=0 AND posts_processed>=0 AND reply_records_returned>=0 AND retweeter_records_returned>=0 AND quote_records_returned>=0 AND unique_users_observed>=0 AND new_users>=0 AND existing_users>=0 AND new_signals>=0 AND existing_signals>=0 AND provider_requests>=0)
);

CREATE TABLE x_intelligence.audience_signals (
    id UUID PRIMARY KEY,
    audience_user_id UUID NOT NULL REFERENCES x_intelligence.audience_users(id) ON DELETE CASCADE,
    competitor_id UUID NOT NULL REFERENCES x_intelligence.competitors(id) ON DELETE CASCADE,
    competitor_post_id UUID NOT NULL REFERENCES x_intelligence.competitor_posts(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('REPLY','RETWEET','QUOTE')),
    source_x_tweet_id TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (audience_user_id, competitor_post_id, signal_type)
);

CREATE TABLE x_intelligence.audience_signal_occurrences (
    id UUID PRIMARY KEY,
    audience_signal_id UUID NOT NULL REFERENCES x_intelligence.audience_signals(id) ON DELETE CASCADE,
    interaction_x_tweet_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (audience_signal_id, interaction_x_tweet_id)
);

CREATE TABLE x_intelligence.audience_collection_progress (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES x_intelligence.audience_collection_runs(id) ON DELETE CASCADE,
    competitor_post_id UUID NOT NULL REFERENCES x_intelligence.competitor_posts(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('REPLY','RETWEET','QUOTE')),
    cursor TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')),
    pages_completed INTEGER NOT NULL DEFAULT 0 CHECK (pages_completed >= 0),
    provider_requests INTEGER NOT NULL DEFAULT 0 CHECK (provider_requests >= 0),
    error_code TEXT,
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, competitor_post_id, signal_type)
);

CREATE INDEX idx_x_audience_users_username_lower ON x_intelligence.audience_users (LOWER(username));
CREATE INDEX idx_x_audience_signals_user ON x_intelligence.audience_signals (audience_user_id);
CREATE INDEX idx_x_audience_signals_competitor ON x_intelligence.audience_signals (competitor_id);
CREATE INDEX idx_x_audience_signals_post ON x_intelligence.audience_signals (competitor_post_id);
CREATE INDEX idx_x_audience_signals_type ON x_intelligence.audience_signals (signal_type);
CREATE INDEX idx_x_audience_runs_competitor_started ON x_intelligence.audience_collection_runs (competitor_id, started_at DESC);
CREATE INDEX idx_x_audience_runs_incomplete ON x_intelligence.audience_collection_runs (status, started_at) WHERE status IN ('RUNNING','PARTIAL','FAILED');
CREATE INDEX idx_x_audience_progress_lookup ON x_intelligence.audience_collection_progress (run_id, status);

COMMIT;
