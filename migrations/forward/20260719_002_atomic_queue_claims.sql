BEGIN;

ALTER TABLE public.outreach_queue
    ADD COLUMN IF NOT EXISTS worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

ALTER TABLE public.delayed_message_queue
    ADD COLUMN IF NOT EXISTS worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

ALTER TABLE public.mass_ppv_queue
    ADD COLUMN IF NOT EXISTS worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

ALTER TABLE public.wall_post_queue
    ADD COLUMN IF NOT EXISTS worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

ALTER TABLE public.webhook_events
    ADD COLUMN IF NOT EXISTS worker_instance_id TEXT,
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_outreach_queue_active_lease
    ON public.outreach_queue (lease_expires_at, worker_instance_id)
    WHERE queue_status = 'processing';
CREATE INDEX IF NOT EXISTS idx_delayed_message_queue_active_lease
    ON public.delayed_message_queue (lease_expires_at, worker_instance_id)
    WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_mass_ppv_queue_active_lease
    ON public.mass_ppv_queue (lease_expires_at, worker_instance_id)
    WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_wall_post_queue_active_lease
    ON public.wall_post_queue (lease_expires_at, worker_instance_id)
    WHERE queue_status = 'processing';
CREATE INDEX IF NOT EXISTS idx_webhook_events_active_lease
    ON public.webhook_events (lease_expires_at, worker_instance_id)
    WHERE status = 'processing';

COMMIT;
