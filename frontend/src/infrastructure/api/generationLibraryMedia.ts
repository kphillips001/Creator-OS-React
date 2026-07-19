type VersionedGenerationMedia = {
  image_id: string;
  generation_date?: string;
  updated_at?: string | null;
  generation_metadata?: Record<string, unknown>;
};

export function generationLibraryMediaUrl(record: VersionedGenerationMedia): string {
  const version = record.generation_metadata?.asset_version
    ?? record.updated_at
    ?? record.generation_date
    ?? record.image_id;
  return `/api/generation-library/media/${encodeURIComponent(record.image_id)}?v=${encodeURIComponent(String(version))}`;
}
