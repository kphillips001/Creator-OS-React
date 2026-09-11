BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.ai_training_work_items) THEN
        RAISE EXCEPTION 'AI Training Queue contains retained workflow history; approved archival is required before rollback.';
    END IF;
END $$;
DROP TABLE IF EXISTS public.ai_training_work_items;
COMMIT;
