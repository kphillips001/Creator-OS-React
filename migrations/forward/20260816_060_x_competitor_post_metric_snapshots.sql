CREATE TABLE IF NOT EXISTS x_intelligence.competitor_post_metric_snapshots (
    id UUID PRIMARY KEY,
    competitor_post_id UUID NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    observation_source TEXT NOT NULL,
    observation_key TEXT NOT NULL,
    view_count BIGINT,
    like_count BIGINT,
    reply_count BIGINT,
    retweet_count BIGINT,
    quote_count BIGINT,
    bookmark_count BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_x_intelligence_post_metric_snapshots_post FOREIGN KEY (competitor_post_id) REFERENCES x_intelligence.competitor_posts(id) ON DELETE CASCADE,
    CONSTRAINT uq_x_intelligence_post_metric_snapshots_observation UNIQUE (competitor_post_id, observation_source, observation_key),
    CONSTRAINT ck_x_intelligence_post_metric_snapshots_source CHECK (observation_source IN ('AUTO_RECENT', 'MANUAL_ARCHIVED')),
    CONSTRAINT ck_x_intelligence_post_metric_snapshots_counts CHECK (
      (view_count IS NULL OR view_count >= 0) AND (like_count IS NULL OR like_count >= 0) AND
      (reply_count IS NULL OR reply_count >= 0) AND (retweet_count IS NULL OR retweet_count >= 0) AND
      (quote_count IS NULL OR quote_count >= 0) AND (bookmark_count IS NULL OR bookmark_count >= 0)
    )
);
CREATE INDEX IF NOT EXISTS idx_x_intelligence_post_metric_snapshots_history ON x_intelligence.competitor_post_metric_snapshots (competitor_post_id, observed_at DESC);
