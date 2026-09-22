BEGIN;

CREATE TABLE IF NOT EXISTS public.x_thread_cta_deliveries (
    delivery_id UUID PRIMARY KEY,
    creator_profile_id BIGINT NOT NULL,
    fanvue_account_id BIGINT NOT NULL,
    publish_operation_id TEXT NOT NULL,
    x_account_name TEXT NOT NULL,
    primary_x_post_id TEXT NOT NULL,
    x_link_attribution_id UUID NOT NULL REFERENCES public.x_link_attributions(x_link_attribution_id) ON DELETE RESTRICT,
    timing TEXT NOT NULL,
    cta_text TEXT NOT NULL DEFAULT '',
    cta_url TEXT NOT NULL,
    state TEXT NOT NULL,
    resulting_x_reply_id TEXT NULL UNIQUE,
    provider_output_url TEXT NULL,
    failure_reason TEXT NULL,
    sent_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_x_thread_cta_delivery_operation UNIQUE (creator_profile_id,fanvue_account_id,publish_operation_id,x_account_name),
    CONSTRAINT uq_x_thread_cta_delivery_parent UNIQUE (creator_profile_id,fanvue_account_id,primary_x_post_id),
    CONSTRAINT ck_x_thread_cta_delivery_parent CHECK (length(btrim(primary_x_post_id)) > 0),
    CONSTRAINT ck_x_thread_cta_delivery_timing CHECK (timing IN ('ASAP','DELAY_30_60')),
    CONSTRAINT ck_x_thread_cta_delivery_state CHECK (state IN ('DELIVERING','POSTED','FAILED','SEND_UNCERTAIN'))
);

CREATE INDEX IF NOT EXISTS idx_x_thread_cta_deliveries_scope
    ON public.x_thread_cta_deliveries (creator_profile_id,fanvue_account_id,created_at DESC);

COMMIT;
