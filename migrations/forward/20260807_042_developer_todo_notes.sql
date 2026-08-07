BEGIN;
ALTER TABLE public.developer_todos ADD COLUMN notes TEXT;
COMMIT;
