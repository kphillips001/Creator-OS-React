ALTER TABLE public.purchase_intents
    ADD COLUMN IF NOT EXISTS purchase_acknowledged_at TIMESTAMPTZ NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_external_event_id
    ON public.webhook_events (external_event_id)
    WHERE external_event_id IS NOT NULL;
