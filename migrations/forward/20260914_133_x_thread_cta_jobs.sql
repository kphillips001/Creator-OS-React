BEGIN;

CREATE TABLE IF NOT EXISTS public.x_thread_cta_jobs (
    job_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    publish_operation_id TEXT NOT NULL,
    social_queue_item_id TEXT NOT NULL,
    generation_image_id TEXT NOT NULL,
    primary_x_post_id TEXT NOT NULL,
    x_account_name TEXT NOT NULL,
    x_link_attribution_id UUID NOT NULL REFERENCES public.x_link_attributions(x_link_attribution_id) ON DELETE RESTRICT,
    asset_reference TEXT NULL,
    thumbnail_reference TEXT NULL,
    caption_preview TEXT NOT NULL DEFAULT '',
    cta_text TEXT NOT NULL,
    cta_url TEXT NOT NULL,
    sampled_delay_seconds INTEGER NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'SCHEDULED',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claim_owner TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    resulting_x_reply_id TEXT NULL UNIQUE,
    provider_output_url TEXT NULL,
    sent_at TIMESTAMPTZ NULL,
    failure_reason TEXT NULL,
    canceled_at TIMESTAMPTZ NULL,
    canceled_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_x_thread_cta_job_operation UNIQUE (creator_profile_id, fanvue_account_id, publish_operation_id, x_account_name),
    CONSTRAINT uq_x_thread_cta_job_primary UNIQUE (creator_profile_id, fanvue_account_id, primary_x_post_id),
    CONSTRAINT ck_x_thread_cta_job_delay CHECK (sampled_delay_seconds BETWEEN 1800 AND 3600),
    CONSTRAINT ck_x_thread_cta_job_state CHECK (state IN ('SCHEDULED','CLAIMED','POSTED','FAILED','SEND_UNCERTAIN','CANCELED'))
);
CREATE INDEX IF NOT EXISTS idx_x_thread_cta_jobs_due ON public.x_thread_cta_jobs (scheduled_at, job_id) WHERE state='SCHEDULED';
CREATE INDEX IF NOT EXISTS idx_x_thread_cta_jobs_scope_history ON public.x_thread_cta_jobs (creator_profile_id, fanvue_account_id, created_at DESC);

COMMIT;
