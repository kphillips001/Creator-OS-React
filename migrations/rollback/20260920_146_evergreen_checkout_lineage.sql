BEGIN;
-- Refuse a rollback that would orphan any committed successor history.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM public.evergreen_checkout_lineage) THEN
        RAISE EXCEPTION 'Evergreen checkout lineage exists; retain audit history and disable the adapter instead';
    END IF;
END $$;
DROP TABLE public.evergreen_checkout_resolution_events;
DROP TABLE public.evergreen_checkout_lineage;
DROP FUNCTION public.guard_evergreen_checkout_lineage();
COMMIT;
