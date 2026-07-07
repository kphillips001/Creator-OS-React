CREATE TABLE IF NOT EXISTS public.ppv_broadcast_logs (
    id BIGSERIAL PRIMARY KEY,
    fanvue_account_id BIGINT NOT NULL,
    fanvue_user_id TEXT NOT NULL,
    campaign_type TEXT NULL,
    content_tag TEXT NOT NULL,
    offer_type TEXT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF to_regclass('public.ppv_broadcast_log') IS NOT NULL THEN
        INSERT INTO public.ppv_broadcast_logs (
            fanvue_account_id,
            fanvue_user_id,
            campaign_type,
            content_tag,
            offer_type,
            status,
            metadata,
            created_at
        )
        SELECT
            source.fanvue_account_id,
            source.fanvue_user_id::text,
            source.campaign_type,
            source.content_tag,
            source.offer_type,
            source.status,
            source.metadata,
            source.created_at
        FROM public.ppv_broadcast_log source
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.ppv_broadcast_logs target
            WHERE target.fanvue_account_id = source.fanvue_account_id
              AND target.fanvue_user_id = source.fanvue_user_id::text
              AND target.content_tag = source.content_tag
              AND target.created_at = source.created_at
        );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ppv_broadcast_logs_account_user_created
    ON public.ppv_broadcast_logs (fanvue_account_id, fanvue_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ppv_broadcast_logs_content_recent
    ON public.ppv_broadcast_logs (fanvue_account_id, fanvue_user_id, content_tag, created_at DESC);
