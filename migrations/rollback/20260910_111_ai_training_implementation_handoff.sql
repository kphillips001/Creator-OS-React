BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.ai_training_work_items
        WHERE status IN ('READY_FOR_IMPLEMENTATION','IMPLEMENTING','NEEDS_VERIFICATION','IMPLEMENTATION_FAILED')
    ) THEN
        RAISE EXCEPTION 'Cannot roll back AI Training implementation handoff while lifecycle items exist';
    END IF;
END $$;
ALTER TABLE public.ai_training_work_items
    DROP CONSTRAINT IF EXISTS ai_training_work_items_linked_future_task_id_fkey;
ALTER TABLE public.ai_training_work_items
    DROP CONSTRAINT IF EXISTS ai_training_work_items_status_check;
ALTER TABLE public.ai_training_work_items
    ADD CONSTRAINT ai_training_work_items_status_check CHECK (status IN (
        'TODO','READY_TO_APPLY','REQUIRES_IMPLEMENTATION','IMPLEMENTED','REJECTED','CLOSED','SUPERSEDED'
    ));

COMMIT;
