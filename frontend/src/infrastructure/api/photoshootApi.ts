import { environment } from "../config/environment";
import type { GenerationRecord } from "../../features/generation-library/types";
import type { CreativeDirectorContext, CreativeDirectorRecommendation, FreeflowIdeaSet, PhotoshootAutoRunRuntime, PhotoshootContext, PhotoshootCurationResult, PhotoshootProvider, PlannedShot, PlanningMode } from "../../features/photoshoot/types";

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
    status?: string;
    image: GenerationRecord | null;
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
      status: item.status || "approved",
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
  request: null | { request_id: string; status: "queued" | "preparation_recovery_required" | "generating" | "finalization_required" | "awaiting_review"; prompt: string; provider_id: string; generation_job_id: string | null; failure: string | null; preparation_recovery_required?: boolean; preparation_error?: string | null; finalization_required?: boolean; finalization_error?: string | null };
  candidate: GenerationRecord | null;
  continuity_assessment?: { status?: "pending" | "completed" | "unavailable"; identity?: string; wardrobe?: string; location?: string; lighting?: string; composition?: string; overall_continuity?: string; reason?: string; warning?: boolean; warning_message?: string };
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
  planning_mode?: PlanningMode; plan_frame_count?: number; session_plan?: PlannedShot[];
  target_shot_count?: number;
  current_shot?: number; planning_shot?: number; remaining_shots?: number; editorial_stage?: string;
  planner_explanation?: string;
  session_plan_index?: number; session_plan_approved?: boolean;
  freeflow_idea_set?: { idea_set_id: string; ideas: string[]; recommended_idea: string; planning_shot: number; approved_shot_count: number; created_at: string; usage: Record<string, string[]> } | null;
  recommendation_state: { inspiration_ideas: string[]; selected_inspiration: string; inspiration_edits?: Record<string, string>; recommendation: CreativeDirectorRecommendation; direction_approved: boolean };
};

const mapFreeflowIdeaSet = (value?: CreativeDirectorContextResponse["freeflow_idea_set"]): FreeflowIdeaSet | null => value ? ({
  ideaSetId: value.idea_set_id,
  ideas: value.ideas || [],
  recommendedIdea: value.recommended_idea || "",
  planningShot: Number(value.planning_shot || 0),
  approvedShotCount: Number(value.approved_shot_count || 0),
  createdAt: value.created_at || "",
  usage: value.usage || {},
}) : null;

export async function getCreativeDirectorContext(sessionId: string, signal?: AbortSignal): Promise<CreativeDirectorContext> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/creative-director/context?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store", signal });
  const result = await response.json().catch(() => ({})) as CreativeDirectorContextResponse & { detail?: string };
  if (!response.ok) throw new Error(result.detail || "Unable to restore Creative Director state.");
  const recommendation = result.recommendation_state?.recommendation || null;
  return {
    sessionId: result.session_id,
    creativeMode: result.creative_mode,
    creatorGuidance: result.creator_guidance || "",
    workflowStage: result.workflow_stage || "ready_for_direction",
    currentPrompt: result.current_prompt || "",
    ideas: result.recommendation_state?.inspiration_ideas || [],
    selectedInspiration: result.recommendation_state?.selected_inspiration || "",
    inspirationEdits: result.recommendation_state?.inspiration_edits || {},
    recommendation: recommendation && (recommendation.title || recommendation.creative_direction) ? recommendation : null,
    directionApproved: Boolean(result.recommendation_state?.direction_approved),
    planningMode: result.planning_mode === "full_plan" ? "full_plan" : "frame_by_frame",
    planFrameCount: Math.max(4, Math.min(12, Number(result.plan_frame_count || 8))),
    targetShotCount: Number(result.target_shot_count) === 0 ? 0 : Math.max(2, Math.min(100, Number(result.target_shot_count || 5))),
    currentShot: Math.max(1, Number(result.current_shot || 1)),
    planningShot: Math.max(2, Number(result.planning_shot || 2)),
    remainingShots: Math.max(0, Number(result.remaining_shots ?? 9)),
    editorialStage: result.editorial_stage || "Beginning",
    plannerExplanation: result.planner_explanation || "Continuing from the latest approved shot.",
    sessionPlan: Array.isArray(result.session_plan) ? result.session_plan : [],
    sessionPlanIndex: Math.max(0, Number(result.session_plan_index || 0)),
    sessionPlanApproved: Boolean(result.session_plan_approved),
    freeflowIdeaSet: mapFreeflowIdeaSet(result.freeflow_idea_set),
  };
}

type InspirationResult = { ideas: string[]; selected_inspiration: string; freeflow_idea_set?: CreativeDirectorContextResponse["freeflow_idea_set"] };
export const requestPhotoshootInspiration = async (body: unknown) => {
  const result = await photoshootMutation<InspirationResult>("/creative-director/inspiration", body);
  return { ...result, freeflowIdeaSet: mapFreeflowIdeaSet(result.freeflow_idea_set) };
};
export const reusePhotoshootInspiration = async (body: unknown) => {
  const result = await photoshootMutation<InspirationResult>("/creative-director/existing-inspiration", body);
  return { ...result, freeflowIdeaSet: mapFreeflowIdeaSet(result.freeflow_idea_set) };
};
export const selectPhotoshootInspiration = (body: unknown) => photoshootMutation<{ selected_inspiration: string; creative_hint: string }>("/creative-director/selection", body);
export const persistPhotoshootGuidance = (body: unknown) => photoshootMutation<{ creator_guidance: string }>("/creative-director/guidance", body);
export const requestPhotoshootRecommendation = (body: unknown) => photoshootMutation<CreativeDirectorRecommendation>("/creative-director/recommendation", body);
export const requestDirectPhotoshootRecommendation = (body: unknown) => photoshootMutation<CreativeDirectorRecommendation>("/creative-director/direct-recommendation", body);
export const approvePhotoshootRecommendation = (body: unknown) => photoshootMutation<{ prompt: string; workflow_stage: string }>("/creative-director/approve", body);
export const chooseAnotherPhotoshootIdea = (body: unknown) => photoshootMutation<{ workflow_stage: string; selected_inspiration: string }>("/creative-director/choose-another", body);
export const setPhotoshootPlanningMode = (body: unknown) => photoshootMutation<{ planning_mode: PlanningMode; plan_frame_count: number; session_plan: PlannedShot[]; session_plan_approved: boolean }>("/creative-director/planning-mode", body);
export const setPhotoshootTargetShotCount = (body: unknown) => photoshootMutation<{ target_shot_count: number }>("/creative-director/target-shot-count", body);
export const extendPhotoshoot = (body: unknown) => photoshootMutation<{
  target_shot_count: number; extended: boolean; current_shot: number; planning_shot: number;
  remaining_shots: number; editorial_stage: string; workflow_stage: string;
}>("/creative-director/extend", body);
export const generatePhotoshootSessionPlan = (body: unknown) => photoshootMutation<{ planning_mode: PlanningMode; plan_frame_count: number; session_plan: PlannedShot[]; session_plan_index: number; session_plan_approved: boolean }>("/creative-director/session-plan", body);
export const approvePhotoshootSessionPlan = (body: unknown) => photoshootMutation<{ session_plan: PlannedShot[]; session_plan_index: number; session_plan_approved: boolean; workflow_stage: string }>("/creative-director/session-plan/approve", body);
export const developPhotoshootPlannedShot = (body: unknown) => photoshootMutation<CreativeDirectorRecommendation>("/creative-director/session-plan/develop", body);
export const advancePhotoshootSessionPlan = (body: unknown) => photoshootMutation<{ session_plan: PlannedShot[]; session_plan_index: number; session_plan_complete: boolean; next_planned_shot: PlannedShot | null; workflow_stage: string }>("/creative-director/session-plan/advance", body);

export const generatePhotoshootShot = (body: unknown) => photoshootMutation<{ request_id: string; generation_job_id: string; operation_id: string; status: string }>("/generate", body);
export const retryPhotoshootFinalization = (body: unknown) => photoshootMutation<{ request_id: string; job_id: string; image_ids: string[]; status: "succeeded" }>("/candidate/retry-finalization", body);
export const retryPhotoshootPreparation = (body: unknown) => photoshootMutation<{ request_id: string; generation_job_id: string; operation_id: string; status: "queued" }>("/candidate/retry-preparation", body);
export const approvePhotoshootCandidate = (body: unknown) => photoshootMutation<{
  success: true;
  request: { request_id: string; status: "approved"; imported_asset_ids: number[] };
  session: Record<string, unknown>;
}>("/candidate/approve", body);
export const regeneratePhotoshootCandidate = (body: unknown) => photoshootMutation("/candidate/regenerate", body);
export const editPhotoshootCandidatePrompt = (body: unknown) => photoshootMutation<{ prompt: string }>("/candidate/edit-prompt", body);
export const rejectPhotoshootCandidate = (body: unknown) => photoshootMutation("/candidate/reject", body);
export const replacePhotoshootShot = (body: unknown) => photoshootMutation<{ success: true; request_id: string; invalidated_request_ids: string[] }>("/shot/replace", body);
export const finishPhotoshoot = (body: unknown) => photoshootMutation<PhotoshootCurationResult>("/finish", body);
export const startPhotoshootAutoRun = (body: unknown) => photoshootMutation<PhotoshootAutoRunRuntime>("/auto-run/start", body);
export const pausePhotoshootAutoRun = (body: unknown) => photoshootMutation<PhotoshootAutoRunRuntime>("/auto-run/pause", body);
export const resumePhotoshootAutoRun = (body: unknown) => photoshootMutation<PhotoshootAutoRunRuntime>("/auto-run/resume", body);
export const stopPhotoshootAutoRun = (body: unknown) => photoshootMutation<PhotoshootAutoRunRuntime>("/auto-run/stop", body);
export const retryPhotoshootAutoRun = (body: unknown) => photoshootMutation<PhotoshootAutoRunRuntime>("/auto-run/retry", body);

export async function getPhotoshootAutoRunRuntime(sessionId: string, signal?: AbortSignal): Promise<PhotoshootAutoRunRuntime> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/auto-run/runtime?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store", signal });
  const result = await response.json().catch(() => ({})) as PhotoshootAutoRunRuntime & { detail?: string };
  if (!response.ok) throw new Error(result.detail || "Unable to refresh Auto Generation status.");
  return result;
}

export async function getPhotoshootStatus(sessionId: string, signal?: AbortSignal): Promise<PhotoshootStatus> {
  const response = await fetch(`${environment.apiBaseUrl}/photoshoot/status?session_id=${encodeURIComponent(sessionId)}`, { cache: "no-store", signal });
  const result = await response.json().catch(() => ({})) as PhotoshootStatus & { detail?: string };
  if (!response.ok) {
    console.error("Photoshoot status failed", { status: response.status, detail: result.detail });
    throw new Error("Unable to refresh Photoshoot generation status.");
  }
  return result;
}
