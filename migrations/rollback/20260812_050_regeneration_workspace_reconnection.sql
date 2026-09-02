DROP INDEX IF EXISTS public.idx_regeneration_runs_workspace_discovery;
ALTER TABLE public.regeneration_runs DROP COLUMN IF EXISTS workspace_dismissed_at;
