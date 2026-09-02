BEGIN;

CREATE TABLE IF NOT EXISTS public.ai_training_subnotes (
  subnote_id TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL,
  training_note_id TEXT NOT NULL,
  title TEXT NOT NULL CHECK (BTRIM(title) <> ''),
  content TEXT NOT NULL DEFAULT '',
  is_completed BOOLEAN NOT NULL DEFAULT FALSE,
  migrated_from_parent_details BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (creator_profile_id, subnote_id),
  CONSTRAINT fk_ai_training_subnotes_parent
    FOREIGN KEY (creator_profile_id, training_note_id)
    REFERENCES public.ai_training_notes(creator_profile_id, note_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_training_subnotes_parent_created
  ON public.ai_training_subnotes(creator_profile_id, training_note_id, created_at, subnote_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_training_subnotes_migrated_parent_details
  ON public.ai_training_subnotes(creator_profile_id, training_note_id)
  WHERE migrated_from_parent_details;

INSERT INTO public.ai_training_subnotes (
  subnote_id, creator_profile_id, training_note_id, title, content,
  migrated_from_parent_details, created_at, updated_at
)
SELECT
  'legacy-' || md5(note.creator_profile_id::text || ':' || note.note_id),
  note.creator_profile_id,
  note.note_id,
  'Existing Note',
  note.details,
  TRUE,
  note.created_at,
  note.updated_at
FROM public.ai_training_notes AS note
WHERE NULLIF(BTRIM(note.details), '') IS NOT NULL
ON CONFLICT DO NOTHING;

COMMIT;
