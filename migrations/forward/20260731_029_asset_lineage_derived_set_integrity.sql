CREATE OR REPLACE FUNCTION public.enforce_single_asset_lineage_derivation_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.asset_lineage_relationships existing
        WHERE existing.derived_asset_id = NEW.derived_asset_id
          AND existing.relationship_id <> NEW.relationship_id
    ) THEN
        RAISE EXCEPTION
            'Derived Asset % already has a canonical derivation relationship set',
            NEW.derived_asset_id
            USING ERRCODE = '23505';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_asset_lineage_single_derivation_set
    ON public.asset_lineage_relationships;

CREATE TRIGGER trg_asset_lineage_single_derivation_set
BEFORE INSERT OR UPDATE OF relationship_id, derived_asset_id
ON public.asset_lineage_relationships
FOR EACH ROW
EXECUTE FUNCTION public.enforce_single_asset_lineage_derivation_set();
