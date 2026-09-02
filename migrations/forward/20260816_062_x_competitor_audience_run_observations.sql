BEGIN;
CREATE TABLE x_intelligence.audience_collection_run_users (
    run_id UUID NOT NULL REFERENCES x_intelligence.audience_collection_runs(id) ON DELETE CASCADE,
    audience_user_id UUID NOT NULL REFERENCES x_intelligence.audience_users(id) ON DELETE CASCADE,
    was_new BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, audience_user_id)
);
CREATE TABLE x_intelligence.audience_collection_run_signals (
    run_id UUID NOT NULL REFERENCES x_intelligence.audience_collection_runs(id) ON DELETE CASCADE,
    audience_signal_id UUID NOT NULL REFERENCES x_intelligence.audience_signals(id) ON DELETE CASCADE,
    was_new BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, audience_signal_id)
);
COMMIT;
