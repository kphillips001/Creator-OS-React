import { environment } from "../config/environment";
import type { VideoConcept, VideoProvider, VideoSession, VideoSettings } from "../../features/video-studio/types";

const base = `${environment.apiBaseUrl}/video-studio`;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  const payload = await response.json().catch(() => null) as T & { error?: string; detail?: string };
  if (!response.ok) throw new Error(payload?.detail || payload?.error || `Video Studio request failed (${response.status}).`);
  return payload;
}
const json = (method: string, body?: unknown): RequestInit => ({ method, headers: { "content-type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

export const videoStudioApi = {
  providers: () => request<{ providers: VideoProvider[] }>("/providers"),
  sessions: () => request<{ sessions: VideoSession[] }>("/sessions"),
  session: (id: string) => request<VideoSession>(`/sessions/${encodeURIComponent(id)}`),
  create: (sourceType: string, sourceId: string, settings: VideoSettings, parent?: { sessionId: string; videoId: string }) => request<VideoSession>("/sessions", json("POST", { source_type: sourceType, source_id: sourceId, settings, parent_session_id: parent?.sessionId, parent_video_id: parent?.videoId })),
  settings: (id: string, settings: Partial<VideoSettings>) => request<VideoSession>(`/sessions/${id}/settings`, json("PATCH", settings)),
  analyze: (id: string) => request<{ visualSceneIntelligence: Record<string, unknown> }>(`/sessions/${id}/analysis`, json("POST")),
  concepts: (id: string, idea?: string) => request<{ concepts: VideoConcept[] }>(`/sessions/${id}/concepts${idea ? "/guided" : ""}`, json("POST", idea ? { idea } : undefined)),
  select: (id: string, conceptId: string) => request<VideoSession>(`/sessions/${id}/concepts/${conceptId}/select`, json("POST")),
  plan: (id: string) => request<{ plan: Record<string, unknown> }>(`/sessions/${id}/plan`, json("POST")),
  generate: (id: string) => request<{ operation: { operationId: string } }>(`/sessions/${id}/generation-runs`, json("POST")),
  extend: (id: string, settings: Partial<VideoSettings>) => request<VideoSession>(`/sessions/${id}/extensions`, json("POST", settings)),
  alternate: (id: string) => request<VideoSession>(`/sessions/${id}/alternates`, json("POST")),
  mediaUrl: (mediaId: string) => `${base}/media/${encodeURIComponent(mediaId)}`,
};

export function videoStudioLink(source: { type: string; id: string; previewUrl?: string | null; label?: string; context?: string }) {
  const params = new URLSearchParams({ sourceType: source.type, sourceId: source.id });
  if (source.previewUrl) params.set("preview", source.previewUrl);
  if (source.label) params.set("label", source.label);
  if (source.context) params.set("context", source.context);
  return `/studio/video?${params}`;
}
