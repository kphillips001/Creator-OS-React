BEGIN;

ALTER TABLE public.developer_todo_subnotes
  DROP COLUMN IF EXISTS is_completed;

COMMIT;
