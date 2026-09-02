BEGIN;

CREATE TABLE public.photoshoot_session_teaser_edit_intents (
  intent_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  deliverable_id UUID NOT NULL REFERENCES public.photoshoot_commerce_deliverables(deliverable_id),
  photoshoot_session_id TEXT NOT NULL,
  source_asset_id BIGINT NOT NULL REFERENCES public.content_items(id),
  source_shot_order INTEGER NOT NULL DEFAULT 1 CHECK (source_shot_order = 1),
  workspace_image_id TEXT NOT NULL UNIQUE,
  result_image_id TEXT,
  teaser_asset_id BIGINT REFERENCES public.content_items(id),
  purpose TEXT NOT NULL DEFAULT 'PHOTOSHOOT_SESSION_TEASER'
    CHECK (purpose = 'PHOTOSHOOT_SESSION_TEASER'),
  status TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX idx_session_teaser_active_creator
  ON public.photoshoot_session_teaser_edit_intents(creator_profile_id)
  WHERE status='ACTIVE';
CREATE INDEX idx_session_teaser_origin
  ON public.photoshoot_session_teaser_edit_intents(deliverable_id,status);

COMMIT;
