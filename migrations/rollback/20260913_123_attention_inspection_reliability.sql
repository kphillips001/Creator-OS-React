BEGIN;

DROP INDEX IF EXISTS public.ux_attention_inspection_request;
ALTER TABLE public.conversation_attention_inspections
  DROP COLUMN IF EXISTS conflict_report,
  DROP COLUMN IF EXISTS request_id;

COMMIT;
