BEGIN;

CREATE TABLE IF NOT EXISTS public.developer_todo_subnotes (
  subnote_id TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL,
  todo_id TEXT NOT NULL,
  title TEXT NOT NULL CHECK (BTRIM(title) <> ''),
  content TEXT NOT NULL DEFAULT '',
  migrated_from_parent_note BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (creator_profile_id, subnote_id),
  CONSTRAINT fk_developer_todo_subnotes_parent
    FOREIGN KEY (creator_profile_id, todo_id)
    REFERENCES public.developer_todos(creator_profile_id, todo_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_developer_todo_subnotes_parent_created
  ON public.developer_todo_subnotes(creator_profile_id, todo_id, created_at, subnote_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_developer_todo_subnotes_migrated_parent_note
  ON public.developer_todo_subnotes(creator_profile_id, todo_id)
  WHERE migrated_from_parent_note;

INSERT INTO public.developer_todo_subnotes (
  subnote_id, creator_profile_id, todo_id, title, content,
  migrated_from_parent_note, created_at, updated_at
)
SELECT
  'legacy-' || md5(todo.creator_profile_id::text || ':' || todo.todo_id),
  todo.creator_profile_id,
  todo.todo_id,
  'Existing Note',
  todo.notes,
  TRUE,
  todo.created_at,
  todo.created_at
FROM public.developer_todos AS todo
WHERE NULLIF(BTRIM(todo.notes), '') IS NOT NULL
ON CONFLICT DO NOTHING;

COMMIT;
