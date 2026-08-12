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
INSERT INTO public.developer_todos (todo_id, creator_profile_id, title, created_at)
SELECT 'add-photoshoot-bundle-support', id, 'Add Photoshoot Bundle Support', '2026-08-07T12:00:00+00:00'::timestamptz
FROM public.creator_profiles
ON CONFLICT (creator_profile_id, todo_id) DO NOTHING;
COMMIT;
