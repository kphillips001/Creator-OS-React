BEGIN;

CREATE TABLE public.ai_training_notes (
  note_id TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  details TEXT,
  integrated BOOLEAN NOT NULL DEFAULT FALSE,
  integrated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (creator_profile_id, note_id)
);

CREATE INDEX idx_ai_training_notes_creator_created
  ON public.ai_training_notes(creator_profile_id, integrated, created_at DESC, note_id DESC);

COMMIT;
