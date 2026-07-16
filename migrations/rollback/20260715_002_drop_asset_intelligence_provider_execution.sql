DROP INDEX IF EXISTS public.idx_asset_intelligence_results_run;
DROP INDEX IF EXISTS public.uq_asset_intelligence_results_execution;
ALTER TABLE public.asset_intelligence_provider_results
    DROP COLUMN IF EXISTS execution_id,
    DROP COLUMN IF EXISTS run_id;
DROP TABLE IF EXISTS public.asset_intelligence_provider_executions;
DROP TABLE IF EXISTS public.asset_intelligence_runs;
