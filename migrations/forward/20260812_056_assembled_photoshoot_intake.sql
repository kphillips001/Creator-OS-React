BEGIN;

ALTER TABLE public.photoshoot_commerce_deliverables
  ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'PHOTOSHOOT_STUDIO'
    CHECK (source_kind IN ('PHOTOSHOOT_STUDIO','GENERATION_LIBRARY_IMPORT')),
  ADD COLUMN source_reference UUID;

CREATE UNIQUE INDEX uq_photoshoot_deliverable_source_reference
  ON public.photoshoot_commerce_deliverables(creator_profile_id,source_kind,source_reference)
  WHERE source_reference IS NOT NULL;

CREATE TABLE public.assembled_photoshoot_intakes (
  intake_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  idempotency_key TEXT NOT NULL,
  display_name TEXT NOT NULL,
  hero_image_id TEXT NOT NULL,
  ordered_image_ids JSONB NOT NULL,
  registered_asset_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'QUEUED'
    CHECK (status IN ('QUEUED','PROCESSING','WAITING_INTELLIGENCE','SUCCEEDED','FAILED')),
  deliverable_id UUID,
  operation_id UUID REFERENCES public.background_operations(operation_id) ON DELETE SET NULL,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE(creator_profile_id,idempotency_key),
  CHECK (jsonb_typeof(ordered_image_ids)='array'),
  CHECK (jsonb_array_length(ordered_image_ids)>=2)
);

CREATE TABLE public.assembled_photoshoot_intake_members (
  intake_id UUID NOT NULL REFERENCES public.assembled_photoshoot_intakes(intake_id) ON DELETE CASCADE,
  image_id TEXT NOT NULL REFERENCES public.generation_library_records(image_id) ON DELETE RESTRICT,
  position INTEGER NOT NULL CHECK (position > 0),
  asset_id BIGINT REFERENCES public.content_items(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(intake_id,image_id),
  UNIQUE(intake_id,position),
  UNIQUE(image_id)
);

CREATE INDEX idx_assembled_photoshoot_intakes_creator_status
  ON public.assembled_photoshoot_intakes(creator_profile_id,status,updated_at DESC);

COMMIT;
