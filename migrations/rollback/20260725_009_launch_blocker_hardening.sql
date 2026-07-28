DROP INDEX IF EXISTS public.idx_webhook_events_external_event_id;

ALTER TABLE public.purchase_intents
    DROP COLUMN IF EXISTS purchase_acknowledged_at;
