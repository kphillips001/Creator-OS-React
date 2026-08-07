BEGIN;
CREATE TABLE public.developer_todos (
  todo_id TEXT NOT NULL,
  creator_profile_id BIGINT NOT NULL REFERENCES public.creator_profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  completed_at TIMESTAMPTZ,
  PRIMARY KEY (creator_profile_id, todo_id)
);
CREATE INDEX idx_developer_todos_creator_created ON public.developer_todos(creator_profile_id, created_at, todo_id);
COMMIT;
