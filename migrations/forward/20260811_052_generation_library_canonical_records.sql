BEGIN;
CREATE TABLE public.generation_library_records (
  image_id TEXT PRIMARY KEY,
  creator_profile_id BIGINT NOT NULL,
  status TEXT NOT NULL,
  record_payload JSONB NOT NULL,
  record_revision BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_generation_library_records_creator_status
  ON public.generation_library_records(creator_profile_id,status,updated_at DESC);
CREATE TABLE public.generation_library_canonical_state (
  store_name TEXT PRIMARY KEY,
  revision BIGINT NOT NULL DEFAULT 0,
  imported_legacy_version TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO public.generation_library_canonical_state(store_name)
VALUES('generation_library') ON CONFLICT DO NOTHING;
COMMIT;
