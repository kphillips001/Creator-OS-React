import { environment } from "../config/environment";

export type VideoGalleryItem = {
  generatedMediaId: string; sessionId: string; title: string; conceptSummary: string | null;
  posterUrl: string; mediaUrl: string; duration: number; resolution: string; width: number | null; height: number | null;
  aspectRatio: string; hasAudio: boolean; providerId: string; providerModel: string; createdAt: string;
  sourceType: string; sourceId: string; sourceLabel: string; sourcePreviewUrl: string | null;
  completionStatus: "COMPLETE" | "PARTIAL"; assetState: "IN_ASSET_LIBRARY" | "NOT_REGISTERED"; finalAssetId: number | null;
  lineage: Record<string, unknown>; extensionAvailable: boolean; alternateGenerationAvailable: boolean;
};

const base = `${environment.apiBaseUrl}/video-gallery`;
async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store" });
  const value = await response.json().catch(() => null) as T & { detail?: string };
  if (!response.ok) throw new Error(value?.detail || "Unable to load Video Gallery.");
  return value;
}
export const videoGalleryApi = {
  list: (query: URLSearchParams) => request<{ items: VideoGalleryItem[]; page: number; pageSize: number; total: number; totalPages: number }>(`?${query}`),
  detail: (id: string) => request<VideoGalleryItem>(`/${encodeURIComponent(id)}`),
};
