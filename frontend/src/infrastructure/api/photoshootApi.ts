import { environment } from "../config/environment";
import type { GenerationRecord } from "../../features/generation-library/types";
import type { CreativeDirectorContext, CreativeDirectorRecommendation, PhotoshootContext, PhotoshootProvider } from "../../features/photoshoot/types";

type PhotoshootContextResponse = {
  creator_profile_exists: boolean;
  pending_photoshoot: GenerationRecord | null;
  active_session: null | {
    session_id: string;
    title: string;
    provider_id: string;
    creative_mode: "safe" | "premium" | "explicit";
    continuity_locks: {
      location: boolean;
      wardrobe: boolean;
      lighting: boolean;
      hairstyle: boolean;
      makeup: boolean;
      camera_style: boolean;
    };
    creative_continuity?: { session_direction?: string; creative_hint?: string; workflow_stage?: string };
  };
  provider_list: PhotoshootProvider[];
  creative_mode: string | null;
  continuity_settings: null | {
    location: boolean;
    wardrobe: boolean;
    lighting: boolean;
    hairstyle: boolean;
    makeup: boolean;
    camera_style: boolean;
  };
  timeline_summary: Array<{
    request_id: string;
    sequence_index: number;
    shot_number: number;
    label: string;
    is_seed: boolean;
    image: GenerationRecord;
  }>;
};

function normalizeCreativeMode(value: string | null): "safe" | "premium" | "explicit" {
  const mode = String(value || "safe").toLowerCase();
  if (mode === "explicit") return "explicit";
  if (mode === "premium" || mode.includes("premium") || mode === "spicy") return "premium";
  return "safe";
}

export async function getPhotoshootContext(signal?: AbortSignal): Promise<PhotoshootContext> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/context`, {
    cache: "no-store",
    method: "GET",
    signal,
  });
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!response.ok) {
    const body = await response.text();
    console.error("Photoshoot Studio context request failed", {
      path: "/photoshoot/context", status: response.status, body,
    });
    throw new Error(response.status === 404
      ? "Photoshoot Studio backend unavailable."
      : "Unable to load Photoshoot Studio.");
  }
  if (!contentType.includes("application/json")) {
    throw new Error("Photoshoot Studio returned a non-JSON response.");
  }
  const result = await response.json() as PhotoshootContextResponse;
  const providers = result.provider_list || [];
  if (!result.creator_profile_exists) {
    return { status: "profile_missing", creatorProfileExists: false, seedImage: null, session: null, providers, timeline: [] };
  }
  if (!result.pending_photoshoot || !result.active_session || !result.continuity_settings) {
    return { status: "photoshoot_missing", creatorProfileExists: true, seedImage: null, session: null, providers, timeline: [] };
  }
  return {
    status: "ready",
    creatorProfileExists: true,
    seedImage: result.pending_photoshoot,
    providers,
    session: {
      sessionId: result.active_session.session_id,
      title: result.active_session.title,
      providerId: result.active_session.provider_id,
      creativeMode: normalizeCreativeMode(result.creative_mode),
      continuityLocks: {
        location: result.continuity_settings.location,
        wardrobe: result.continuity_settings.wardrobe,
        lighting: result.continuity_settings.lighting,
        hairstyle: result.continuity_settings.hairstyle,
        makeup: result.continuity_settings.makeup,
        cameraStyle: result.continuity_settings.camera_style,
      },
      sessionDirection: String(result.active_session.creative_continuity?.session_direction || ""),
      creativeHint: String(result.active_session.creative_continuity?.creative_hint || ""),
      workflowStage: String(result.active_session.creative_continuity?.workflow_stage || "ready_for_direction"),
    },
    timeline: (result.timeline_summary || []).map((item) => ({
      requestId: item.request_id,
      sequenceIndex: item.sequence_index,
      shotNumber: item.shot_number,
      label: item.label,
      isSeed: item.is_seed,
      image: item.image,
    })),
  };
}

export async function returnPhotoshootToLibrary(): Promise<string> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/return-to-library`, { method: "POST" });
  const body = await response.json().catch(() => ({})) as { redirect?: string; detail?: string };
  if (!response.ok) {
    console.error("Photoshoot return request failed", { status: response.status, detail: body.detail });
    throw new Error(body.detail || "Unable to return this image to Generation Library.");
  }
  return body.redirect || "/library/generations";
}

export async function stopPhotoshootAndReturnSeed(): Promise<{ redirect: string; message: string }> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/stop-and-return-seed`, { method: "POST" });
  const body = await response.json().catch(() => ({})) as { redirect?: string; message?: string; detail?: string };
  if (!response.ok) {
    console.error("Photoshoot stop request failed", { status: response.status, detail: body.detail });
    throw new Error(body.detail || "Unable to stop this Photoshoot.");
  }
  return { redirect: body.redirect || "/library/generations", message: body.message || "Photoshoot stopped. Seed returned to Generation Library." };
}

export type PhotoshootStatus = {
  request: null | { request_id: string; status: "queued" | "generating" | "awaiting_review"; prompt: string; provider_id: string; generation_job_id: string | null; failure: string | null };
  candidate: GenerationRecord | null;
};

async function photoshootMutation<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot${path}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const result = await response.json().catch(() => ({})) as T & { detail?: string };
  if (!response.ok) {
    console.error("Photoshoot action failed", { path, status: response.status, detail: result.detail });
    throw new Error(result.detail || "Photoshoot action failed. Please try again.");
  }
  return result;
}

type CreativeDirectorContextResponse = {
  session_id: string; creative_mode: "safe" | "premium" | "explicit"; session_direction: string;
  creator_guidance: string; workflow_stage: string; current_prompt: string;
  recommendation_state: { inspiration_ideas: string[]; selected_inspiration: string; recommendation: CreativeDirectorRecommendation; direction_approved: boolean };
};

export async function getCreativeDirectorContext(sessionId: string, signal?: AbortSignal): Promise<CreativeDirectorContext> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/creative-director/context?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store", signal });
  const result = await response.json().catch(() => ({})) as CreativeDirectorContextResponse & { detail?: string };
  if (!response.ok) throw new Error(result.detail || "Unable to restore Creative Director state.");
  const recommendation = result.recommendation_state?.recommendation || null;
  return { sessionId: result.session_id, creativeMode: result.creative_mode, creatorGuidance: result.creator_guidance || "", workflowStage: result.workflow_stage || "ready_for_direction", currentPrompt: result.current_prompt || "", ideas: result.recommendation_state?.inspiration_ideas || [], selectedInspiration: result.recommendation_state?.selected_inspiration || "", recommendation: recommendation && (recommendation.title || recommendation.creative_direction) ? recommendation : null, directionApproved: Boolean(result.recommendation_state?.direction_approved) };
}

export const requestPhotoshootInspiration = (body: unknown) => photoshootMutation<{ ideas: string[]; selected_inspiration: string }>("/creative-director/inspiration", body);
export const selectPhotoshootInspiration = (body: unknown) => photoshootMutation<{ selected_inspiration: string; creative_hint: string }>("/creative-director/selection", body);
export const persistPhotoshootGuidance = (body: unknown) => photoshootMutation<{ creator_guidance: string }>("/creative-director/guidance", body);
export const requestPhotoshootRecommendation = (body: unknown) => photoshootMutation<CreativeDirectorRecommendation>("/creative-director/recommendation", body);
export const approvePhotoshootRecommendation = (body: unknown) => photoshootMutation<{ prompt: string; workflow_stage: string }>("/creative-director/approve", body);
export const chooseAnotherPhotoshootIdea = (body: unknown) => photoshootMutation<{ workflow_stage: string; selected_inspiration: string }>("/creative-director/choose-another", body);

export const generatePhotoshootShot = (body: unknown) => photoshootMutation<{ request_id: string; status: string }>("/generate", body);
export const approvePhotoshootCandidate = (body: unknown) => photoshootMutation<{
  success: true;
  request: { request_id: string; status: "approved"; imported_asset_ids: number[] };
  session: Record<string, unknown>;
}>("/candidate/approve", body);
export const regeneratePhotoshootCandidate = (body: unknown) => photoshootMutation("/candidate/regenerate", body);
export const editPhotoshootCandidatePrompt = (body: unknown) => photoshootMutation<{ prompt: string }>("/candidate/edit-prompt", body);
export const rejectPhotoshootCandidate = (body: unknown) => photoshootMutation("/candidate/reject", body);
export const finishPhotoshoot = (body: unknown) => photoshootMutation<{ status: "completed"; approved_shot_count: number; gallery_ready: boolean }>("/finish", body);

export async function getPhotoshootStatus(sessionId: string, signal?: AbortSignal): Promise<PhotoshootStatus> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/status?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store", signal });
  const result = await response.json().catch(() => ({})) as PhotoshootStatus & { detail?: string };
  if (!response.ok) {
    console.error("Photoshoot status failed", { status: response.status, detail: result.detail });
    throw new Error("Unable to refresh Photoshoot generation status.");
  }
  return result;
}
