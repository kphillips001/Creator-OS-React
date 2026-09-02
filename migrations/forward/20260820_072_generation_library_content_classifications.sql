BEGIN;
CREATE TABLE public.generation_library_content_classifications (
  image_id TEXT PRIMARY KEY REFERENCES public.generation_library_records(image_id) ON DELETE CASCADE,
  content_classification TEXT NOT NULL CHECK (content_classification IN ('SFW', 'NSFW')),
  classification_source TEXT NOT NULL CHECK (classification_source = 'MANUAL'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_generation_library_content_classification
  ON public.generation_library_content_classifications(content_classification, image_id);
COMMIT;
