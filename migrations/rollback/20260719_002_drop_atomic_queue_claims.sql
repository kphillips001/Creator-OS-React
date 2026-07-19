BEGIN;

DROP INDEX IF EXISTS public.idx_webhook_events_active_lease;
DROP INDEX IF EXISTS public.idx_wall_post_queue_active_lease;
DROP INDEX IF EXISTS public.idx_mass_ppv_queue_active_lease;
DROP INDEX IF EXISTS public.idx_delayed_message_queue_active_lease;
DROP INDEX IF EXISTS public.idx_outreach_queue_active_lease;

ALTER TABLE public.webhook_events DROP COLUMN IF EXISTS lease_expires_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS worker_instance_id;
ALTER TABLE public.wall_post_queue DROP COLUMN IF EXISTS lease_expires_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS worker_instance_id;
ALTER TABLE public.mass_ppv_queue DROP COLUMN IF EXISTS lease_expires_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS worker_instance_id;
ALTER TABLE public.delayed_message_queue DROP COLUMN IF EXISTS lease_expires_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS worker_instance_id;
ALTER TABLE public.outreach_queue DROP COLUMN IF EXISTS lease_expires_at, DROP COLUMN IF EXISTS claimed_at, DROP COLUMN IF EXISTS worker_instance_id;

COMMIT;
