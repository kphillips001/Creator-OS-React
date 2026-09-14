BEGIN;

ALTER TABLE public.conversation_attention_inspections
  ADD COLUMN request_id UUID NULL,
  ADD COLUMN conflict_report JSONB NULL;

CREATE UNIQUE INDEX ux_attention_inspection_request
  ON public.conversation_attention_inspections(request_id)
  WHERE request_id IS NOT NULL;

COMMIT;
