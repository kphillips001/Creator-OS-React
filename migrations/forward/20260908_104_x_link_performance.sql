BEGIN;

CREATE TABLE IF NOT EXISTS public.x_link_attributions (
    x_link_attribution_id UUID PRIMARY KEY,
    attribution_token TEXT NOT NULL UNIQUE,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    publish_operation_id TEXT NOT NULL,
    social_queue_item_id TEXT NOT NULL,
    generation_image_id TEXT NOT NULL,
    primary_x_post_id TEXT NOT NULL,
    cta_x_post_id TEXT NULL UNIQUE,
    x_account_name TEXT NOT NULL,
    primary_caption TEXT NOT NULL,
    primary_published_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_x_link_attribution_publish_operation
        UNIQUE (creator_profile_id, fanvue_account_id, publish_operation_id, x_account_name),
    CONSTRAINT ck_x_link_attribution_status
        CHECK (status IN ('ACTIVE', 'REVOKED'))
);

CREATE INDEX IF NOT EXISTS idx_x_link_attributions_scope_published
    ON public.x_link_attributions
    (creator_profile_id, fanvue_account_id, primary_published_at DESC);
CREATE INDEX IF NOT EXISTS idx_x_link_attributions_queue_item
    ON public.x_link_attributions (social_queue_item_id);

CREATE TABLE IF NOT EXISTS public.x_link_click_events (
    event_id UUID PRIMARY KEY,
    x_link_attribution_id UUID NOT NULL
        REFERENCES public.x_link_attributions(x_link_attribution_id) ON DELETE RESTRICT,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    classification TEXT NOT NULL,
    classification_reason TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    CONSTRAINT ck_x_link_click_event_type
        CHECK (event_type = 'X_TELEGRAM_CTA_HANDOFF'),
    CONSTRAINT ck_x_link_click_classification
        CHECK (classification = 'LIKELY_BROWSER'),
    CONSTRAINT ck_x_link_click_schema_version CHECK (schema_version = 1)
);

CREATE INDEX IF NOT EXISTS idx_x_link_click_events_attribution_occurred
    ON public.x_link_click_events (x_link_attribution_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_x_link_click_events_occurred
    ON public.x_link_click_events (occurred_at);

COMMIT;
