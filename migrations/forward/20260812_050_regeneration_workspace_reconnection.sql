ALTER TABLE public.regeneration_runs
    ADD COLUMN IF NOT EXISTS workspace_dismissed_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_regeneration_runs_workspace_discovery
    ON public.regeneration_runs (creator_profile_id, updated_at DESC)
    WHERE workspace_dismissed_at IS NULL;
