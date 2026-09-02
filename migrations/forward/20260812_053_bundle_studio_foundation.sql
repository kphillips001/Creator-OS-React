BEGIN;

CREATE TABLE public.bundle_studio_bundles (
  bundle_id UUID PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE'
    CHECK (status IN ('ACTIVE','ABANDONED','COMPLETED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_bundle_studio_active_workspace
  ON public.bundle_studio_bundles(creator_profile_id) WHERE status='ACTIVE';

CREATE TABLE public.bundle_studio_members (
  bundle_id UUID NOT NULL REFERENCES public.bundle_studio_bundles(bundle_id) ON DELETE CASCADE,
  image_id TEXT NOT NULL REFERENCES public.generation_library_records(image_id) ON DELETE RESTRICT,
  position INTEGER NOT NULL CHECK (position > 0),
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(bundle_id,image_id),
  UNIQUE(bundle_id,position)
);

CREATE TABLE public.generation_image_dispositions (
  image_id TEXT PRIMARY KEY REFERENCES public.generation_library_records(image_id) ON DELETE CASCADE,
  owner TEXT NOT NULL CHECK (owner IN ('BUNDLE_STUDIO')),
  owner_id UUID NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_generation_image_dispositions_owner
  ON public.generation_image_dispositions(owner,owner_id);

COMMIT;
