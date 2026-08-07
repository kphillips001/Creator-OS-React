BEGIN;
CREATE TABLE public.video_generation_sessions (
 session_id UUID PRIMARY KEY, creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
 account_id BIGINT REFERENCES public.fanvue_accounts(id), status TEXT NOT NULL DEFAULT 'DRAFT',
 source_type TEXT NOT NULL, source_id TEXT NOT NULL, source_asset_id BIGINT REFERENCES public.content_items(id),
 source_media_type TEXT NOT NULL, source_version TEXT NOT NULL, source_lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
 source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb, settings JSONB NOT NULL, settings_version INTEGER NOT NULL DEFAULT 1,
 provider_id TEXT NOT NULL, provider_capability JSONB NOT NULL, visual_intelligence JSONB,
 visual_intelligence_cache_key TEXT, concept_batches JSONB NOT NULL DEFAULT '[]'::jsonb,
 selected_concept JSONB, custom_guidance TEXT, execution_plan JSONB, current_generation_run UUID,
 final_generated_media_id UUID, final_asset_id BIGINT REFERENCES public.content_items(id),
 parent_session_id UUID REFERENCES public.video_generation_sessions(session_id), parent_video_id UUID,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_video_sessions_owner ON public.video_generation_sessions(creator_profile_id, account_id, created_at DESC);
CREATE UNIQUE INDEX uq_video_intelligence_cache ON public.video_generation_sessions(creator_profile_id, visual_intelligence_cache_key)
 WHERE visual_intelligence IS NOT NULL;
CREATE TABLE public.video_generation_segments (
 segment_id UUID PRIMARY KEY, session_id UUID NOT NULL REFERENCES public.video_generation_sessions(session_id) ON DELETE CASCADE,
 generation_run_id UUID NOT NULL, ordinal INTEGER NOT NULL, generation_type TEXT NOT NULL,
 planned_duration INTEGER NOT NULL, actual_duration NUMERIC, status TEXT NOT NULL DEFAULT 'PLANNED',
 input_source JSONB NOT NULL DEFAULT '{}'::jsonb, provider_id TEXT NOT NULL, provider_task_id TEXT,
 generation_job_id TEXT, idempotency_key TEXT NOT NULL, prompt_snapshot TEXT NOT NULL,
 request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, provider_response JSONB,
 output_clip TEXT, output_hash TEXT, failure_code TEXT, failure_message TEXT,
 attempt_count INTEGER NOT NULL DEFAULT 0, dispatch_started_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), completed_at TIMESTAMPTZ,
 UNIQUE(generation_run_id, ordinal), UNIQUE(idempotency_key)
);
CREATE INDEX idx_video_segments_session_run ON public.video_generation_segments(session_id,generation_run_id,ordinal);
CREATE TABLE public.generated_media (
 media_id UUID PRIMARY KEY, creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id),
 account_id BIGINT REFERENCES public.fanvue_accounts(id), media_type TEXT NOT NULL CHECK(media_type IN ('image','video')),
 media_path TEXT NOT NULL, poster_path TEXT, duration_seconds NUMERIC, width INTEGER, height INTEGER,
 provider_id TEXT, generation_job_id TEXT, source_lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
 provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, prompt_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 generation_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
