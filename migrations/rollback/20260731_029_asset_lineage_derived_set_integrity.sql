DROP TRIGGER IF EXISTS trg_asset_lineage_single_derivation_set
    ON public.asset_lineage_relationships;
DROP FUNCTION IF EXISTS public.enforce_single_asset_lineage_derivation_set();
