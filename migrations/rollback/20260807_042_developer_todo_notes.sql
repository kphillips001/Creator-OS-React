BEGIN;
ALTER TABLE public.developer_todos DROP COLUMN IF EXISTS notes;
COMMIT;
