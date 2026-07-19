import { environment } from "../config/environment";
import type {
  EditStudioProvider,
  EditStudioContext,
  EditMode,
  EditStudioReferenceAsset,
  ReferenceSource,
} from "../../features/edit-studio/types";
import type { GenerationRecord } from "../../features/generation-library/types";

type EditStudioContextResponse = {
  creator_profile_exists: boolean;
  pending_source: GenerationRecord | null;
  candidate: GenerationRecord | null;
  providers: EditStudioProvider[];
};

type EditStudioReferenceResponse = {
  asset_id: number;
  label: string;
  preview_url: string;
};

type EditStudioActionResponse = { success: boolean; message: string };

export type GenerateEditInput = {
  sourceImageId: string;
  originalSourceImageId: string;
  editMode: EditMode;
  providerId: string;
  prompt: string;
  references: Array<{ source: ReferenceSource; assetId: number }>;
};

export type EditGenerationStatus = {
  generationJobId: string;
  generationStatus: string;
  providerId: string;
  candidate: GenerationRecord | null;
  error: string | null;
};

async function readEditStudioJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${environment.apiBaseUrl}${path}`, { signal, cache: "no-store" });
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  const body = await response.text();
  if (!response.ok) {
    const message = response.status === 404
      ? "Edit Studio backend unavailable."
      : response.status >= 500
        ? "Unable to load Edit Studio."
        : `Edit Studio request failed with HTTP ${response.status}`;
    if (contentType.includes("application/json") && body) {
      try {
        const result = JSON.parse(body) as { error?: string; detail?: string };
        console.error("Edit Studio backend request failed", {
          path, status: response.status, error: result.error || result.detail, body,
        });
      } catch {
        console.error("Edit Studio backend request failed", { path, status: response.status, body });
      }
    } else {
      console.error("Edit Studio backend request failed", { path, status: response.status, body });
    }
    throw new Error(message);
  }
  if (!contentType.includes("application/json")) {
    throw new Error("Edit Studio returned a non-JSON response");
  }
  try {
    return JSON.parse(body) as T;
  } catch {
    throw new Error("Edit Studio returned invalid JSON");
  }
}

async function sendEditStudioJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${environment.apiBaseUrl}${path}`, init);
  const body = await response.text();
  if (!response.ok) {
    let detail = `Edit Studio request failed with HTTP ${response.status}`;
    try {
      const parsed = JSON.parse(body) as { detail?: string; error?: string };
      detail = parsed.detail || parsed.error || detail;
    } catch {
      // Preserve the safe HTTP fallback when the response is not JSON.
    }
    console.error("Edit Studio action failed", { path, status: response.status, body });
    throw new Error(detail);
  }
  return JSON.parse(body) as T;
}

export async function getEditStudioContext(signal?: AbortSignal): Promise<EditStudioContext> {
  const result = await readEditStudioJson<EditStudioContextResponse>(
    "/edit-studio/context",
    signal,
  );
  if (!result.creator_profile_exists) {
    return { status: "profile_missing", creatorProfileExists: false, pendingImage: null, candidateImage: null, providers: result.providers };
  }
  if (!result.pending_source) {
    return { status: "image_missing", creatorProfileExists: true, pendingImage: null, candidateImage: null, providers: result.providers };
  }
  return { status: "ready", creatorProfileExists: true, pendingImage: result.pending_source, candidateImage: result.candidate, providers: result.providers };
}

export async function getEditStudioReferences(signal?: AbortSignal): Promise<EditStudioReferenceAsset[]> {
  const result = await readEditStudioJson<EditStudioReferenceResponse[]>("/edit-studio/references", signal);
  return result.map((reference) => ({
    assetId: reference.asset_id,
    label: reference.label,
    previewUrl: reference.preview_url,
  }));
}

export async function uploadEditStudioReference(file: File): Promise<EditStudioReferenceAsset> {
  const form = new FormData();
  form.append("image", file);
  const result = await sendEditStudioJson<EditStudioReferenceResponse>("/edit-studio/references/upload", {
    method: "POST",
    body: form,
  });
  return { assetId: result.asset_id, label: result.label, previewUrl: result.preview_url };
}

export function returnEditStudioToLibrary(): Promise<EditStudioActionResponse> {
  return sendEditStudioJson("/edit-studio/return-to-library", { method: "POST" });
}

export function generateEdit(input: GenerateEditInput): Promise<{
  success: boolean; message: string; generation_job_id: string; generation_status: string;
}> {
  return sendEditStudioJson("/edit-studio/generate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source_image_id: input.sourceImageId,
      original_source_image_id: input.originalSourceImageId,
      edit_mode: input.editMode,
      provider_id: input.providerId,
      prompt: input.prompt,
      references: input.references.map((reference) => ({
        source: reference.source,
        asset_id: reference.assetId,
      })),
    }),
  });
}

export async function getEditGenerationStatus(jobId: string, signal?: AbortSignal): Promise<EditGenerationStatus> {
  const result = await readEditStudioJson<{
    generation_job_id: string;
    generation_status: string;
    provider_id: string;
    candidate: GenerationRecord | null;
    error: string | null;
  }>(`/edit-studio/generation/${encodeURIComponent(jobId)}`, signal);
  return {
    generationJobId: result.generation_job_id,
    generationStatus: result.generation_status,
    providerId: result.provider_id,
    candidate: result.candidate,
    error: result.error,
  };
}

export async function approveEditCandidate(candidateImageId: string): Promise<EditStudioActionResponse & { updatedRecord: GenerationRecord }> {
  const result = await sendEditStudioJson<EditStudioActionResponse & { updated_record: GenerationRecord }>("/edit-studio/approve", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ candidate_image_id: candidateImageId }),
  });
  return { success: result.success, message: result.message, updatedRecord: result.updated_record };
}

export async function editCandidateAgain(candidateImageId: string): Promise<GenerationRecord> {
  const result = await sendEditStudioJson<EditStudioActionResponse & { working_source: GenerationRecord }>("/edit-studio/edit-again", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ candidate_image_id: candidateImageId }),
  });
  return result.working_source;
}

export function discardEditCandidate(candidateImageId: string): Promise<EditStudioActionResponse> {
  return sendEditStudioJson("/edit-studio/discard", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ candidate_image_id: candidateImageId }),
  });
}
