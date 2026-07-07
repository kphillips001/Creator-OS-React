-- Migration-control baseline for legacy/provider tables that predate the
-- Creator OS forward migration stream. This migration is intentionally
-- additive and non-destructive: it creates missing compatibility tables,
-- adds production lookup indexes, and documents ownership/status.

CREATE TABLE IF NOT EXISTS public.automated_reactions (
    id SERIAL PRIMARY KEY,
    external_event_id TEXT,
    fanvue_user_id TEXT,
    fanvue_account_id TEXT,
    local_user_id INTEGER,
    reaction_type TEXT NOT NULL,
    message_text TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    execution_mode TEXT,
    blocked_reason TEXT,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.delayed_message_queue (
    id SERIAL PRIMARY KEY,
    fanvue_account_id BIGINT,
    fanvue_user_id TEXT NOT NULL,
    message_body TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    scheduled_for TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    last_error TEXT,
    fanvue_message_id TEXT,
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.fanvue_chat_messages (
    id SERIAL PRIMARY KEY,
    fanvue_account_id INTEGER NOT NULL,
    fanvue_user_uuid TEXT NOT NULL,
    fanvue_message_uuid TEXT NOT NULL UNIQUE,
    sender_uuid TEXT,
    message_text TEXT,
    sent_at TIMESTAMP,
    is_inbound BOOLEAN DEFAULT FALSE,
    raw_payload TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.outreach_queue (
    id SERIAL PRIMARY KEY,
    fanvue_account_id INTEGER NOT NULL,
    fanvue_user_id INTEGER NOT NULL,
    outreach_type TEXT NOT NULL DEFAULT 'reactivation',
    queue_status TEXT NOT NULL DEFAULT 'pending',
    scheduled_for TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.send_log (
    id SERIAL PRIMARY KEY,
    fanvue_account_id INTEGER,
    fanvue_user_id INTEGER,
    fanvue_user_uuid TEXT,
    message_type TEXT,
    route TEXT,
    offer_type TEXT,
    content_tag TEXT,
    price NUMERIC(10, 2),
    payload JSONB,
    response JSONB,
    send_status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.wall_post_history (
    id SERIAL PRIMARY KEY,
    fanvue_account_id INTEGER NOT NULL,
    content_item_id INTEGER NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    wall_status TEXT NOT NULL,
    delivery_method TEXT NOT NULL,
    fanvue_post_uuid TEXT,
    scheduled_for TIMESTAMP,
    posted_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (fanvue_account_id, content_item_id)
);

CREATE TABLE IF NOT EXISTS public.wall_post_queue (
    id SERIAL PRIMARY KEY,
    fanvue_account_id INTEGER NOT NULL,
    content_item_id INTEGER NOT NULL REFERENCES public.content_items(id) ON DELETE CASCADE,
    queue_status TEXT NOT NULL DEFAULT 'pending',
    scheduled_for TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_automated_reactions_account_status
    ON public.automated_reactions (fanvue_account_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_automated_reactions_external_event
    ON public.automated_reactions (external_event_id);

CREATE INDEX IF NOT EXISTS idx_delayed_message_queue_due
    ON public.delayed_message_queue (status, scheduled_for, id);
CREATE INDEX IF NOT EXISTS idx_delayed_message_queue_account_status
    ON public.delayed_message_queue (fanvue_account_id, status, scheduled_for);

CREATE INDEX IF NOT EXISTS idx_fanvue_chat_messages_account_user_sent
    ON public.fanvue_chat_messages (fanvue_account_id, fanvue_user_uuid, sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_outreach_queue_due
    ON public.outreach_queue (queue_status, scheduled_for, id);
CREATE INDEX IF NOT EXISTS idx_outreach_queue_account_status
    ON public.outreach_queue (fanvue_account_id, queue_status, scheduled_for);

CREATE INDEX IF NOT EXISTS idx_send_log_account_user_created
    ON public.send_log (fanvue_account_id, fanvue_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_send_log_status_created
    ON public.send_log (send_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wall_post_queue_due
    ON public.wall_post_queue (queue_status, scheduled_for, id);
CREATE INDEX IF NOT EXISTS idx_wall_post_queue_account_status
    ON public.wall_post_queue (fanvue_account_id, queue_status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_wall_post_history_content
    ON public.wall_post_history (content_item_id);

CREATE INDEX IF NOT EXISTS idx_purchase_events_account_user_purchase
    ON public.purchase_events (fanvue_account_id, fanvue_user_id, purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_qualification_ppv_events_account_user_created
    ON public.qualification_ppv_events (fanvue_account_id, fanvue_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_offers_sent_account_user_created
    ON public.offers_sent (fanvue_account_id, fanvue_user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_mass_ppv_queue_status_due
    ON public.mass_ppv_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_mass_ppv_campaigns_account_status
    ON public.mass_ppv_campaigns (fanvue_account_id, status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status_retry
    ON public.webhook_events (status, next_retry_at);

COMMENT ON TABLE public.automated_reactions IS 'Owner=Automated Reaction; Status=CANONICAL; Repository=AutomatedReactionRepository';
COMMENT ON TABLE public.buyer_intelligence IS 'Owner=Customer Intelligence; Status=CANONICAL; Repository=BuyerIntelligenceRepository';
COMMENT ON TABLE public.chat_messages IS 'Owner=Conversation Operations; Status=PROVIDER_SPECIFIC; Repository=ChatMessageRepository';
COMMENT ON TABLE public.chat_threads IS 'Owner=Conversation Operations; Status=PROVIDER_SPECIFIC; Repository=ChatMessageRepository';
COMMENT ON TABLE public.cms_fanvue_upload_links IS 'Owner=Publishing; Status=PROVIDER_SPECIFIC; Repository=CmsFanvueUploadRepository';
COMMENT ON TABLE public.content_catalog IS 'Owner=Legacy Content Catalog; Status=LEGACY; Repository=ContentRepository';
COMMENT ON TABLE public.content_usage_log IS 'Owner=Business Learning; Status=CANONICAL; Repository=ContentUsageRepository';
COMMENT ON TABLE public.creator_profiles IS 'Owner=Creator Workspace; Status=CANONICAL; Repository=CreatorProfileRepository';
COMMENT ON TABLE public.delayed_message_queue IS 'Owner=Activity Feed; Status=CANONICAL; Repository=DelayedMessageQueueRepository';
COMMENT ON TABLE public.fanvue_accounts IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=FanvueAccountRepository';
COMMENT ON TABLE public.fanvue_chat_messages IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=FanvueMessageRepository';
COMMENT ON TABLE public.fanvue_messages IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=FanvueMessageSyncRepository';
COMMENT ON TABLE public.fanvue_monetization_events IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=MonetizationEventRepository';
COMMENT ON TABLE public.fanvue_threads IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=FanvueMessageSyncRepository';
COMMENT ON TABLE public.fanvue_users IS 'Owner=Fanvue Provider; Status=PROVIDER_SPECIFIC; Repository=FanvueUserRepository';
COMMENT ON TABLE public.mass_ppv_campaigns IS 'Owner=Mass PPV; Status=CANONICAL; Repository=MassPpvCampaignRepository';
COMMENT ON TABLE public.mass_ppv_queue IS 'Owner=Mass PPV; Status=CANONICAL; Repository=MassPpvCampaignRepository';
COMMENT ON TABLE public.offers_sent IS 'Owner=Commerce Execution; Status=CANONICAL; Repository=OfferService';
COMMENT ON TABLE public.outreach_log IS 'Owner=Outreach; Status=CANONICAL; Repository=OutreachLogRepository';
COMMENT ON TABLE public.outreach_queue IS 'Owner=Outreach; Status=CANONICAL; Repository=OutreachQueueRepository';
COMMENT ON TABLE public.ppv_broadcast_log IS 'Owner=PPV Broadcast; Status=CANDIDATE_FOR_RETIREMENT; Repository=None';
COMMENT ON TABLE public.ppv_broadcast_logs IS 'Owner=PPV Broadcast; Status=CANONICAL; Repository=PpvBroadcastRepository';
COMMENT ON TABLE public.purchase_events IS 'Owner=Commerce Intelligence; Status=CANONICAL; Repository=MonetizationEventRepository';
COMMENT ON TABLE public.qualification_ppv_events IS 'Owner=Qualification PPV; Status=CANONICAL; Repository=QualificationPpvRepository';
COMMENT ON TABLE public.send_log IS 'Owner=Runtime Send Log; Status=COMPATIBILITY; Repository=SendLogRepository';
COMMENT ON TABLE public.user_memory IS 'Owner=Customer Intelligence; Status=CANONICAL; Repository=MemoryRepository';
COMMENT ON TABLE public.wall_post_history IS 'Owner=Wall Scheduler; Status=CANONICAL; Repository=WallPostRepository';
COMMENT ON TABLE public.wall_post_queue IS 'Owner=Wall Scheduler; Status=CANONICAL; Repository=WallPostRepository';
COMMENT ON TABLE public.webhook_events IS 'Owner=Webhook Ingestion; Status=CANONICAL; Repository=WebhookEventRepository';
