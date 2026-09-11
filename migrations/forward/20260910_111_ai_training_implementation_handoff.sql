BEGIN;

ALTER TABLE public.ai_training_work_items
    DROP CONSTRAINT IF EXISTS ai_training_work_items_status_check;
ALTER TABLE public.ai_training_work_items
    ADD CONSTRAINT ai_training_work_items_status_check CHECK (status IN (
        'TODO','READY_TO_APPLY','REQUIRES_IMPLEMENTATION',
        'READY_FOR_IMPLEMENTATION','IMPLEMENTING','NEEDS_VERIFICATION',
        'IMPLEMENTATION_FAILED','IMPLEMENTED','REJECTED','CLOSED','SUPERSEDED'
    ));
ALTER TABLE public.ai_training_work_items
    DROP CONSTRAINT IF EXISTS ai_training_work_items_linked_future_task_id_fkey;
ALTER TABLE public.ai_training_work_items
    ADD CONSTRAINT ai_training_work_items_linked_future_task_id_fkey
    FOREIGN KEY (linked_future_task_id) REFERENCES public.developer_agent_tasks(task_id);

COMMIT;
