import { environment } from "../config/environment";
import type { ContentStudioContext } from "../../features/content-studio/types/contentStudioContext";
import type { ContentStudioConfiguration } from "../../features/content-studio/types/contentStudioConfiguration";
import type { CreativeTagActionResponse } from "../../features/content-studio/types/contentStudioCreativeTools";
import type {
  PromptWorkshopArchiveResponse,
  PromptWorkshopBatch,
  PromptWorkshopBatchResponse,
  PromptWorkshopLane,
} from "../../features/content-studio/types/promptWorkshop";
import type {
  PromptPreview,
  PromptPreviewResponse,
} from "../../features/content-studio/types/promptPreview";
import type { PromptPlannerResponse } from "../../features/content-studio/types/promptPlanner";
import type { ContentStudioGeneration, GenerationSubmission } from "../../features/content-studio/types/generation";

type ContentStudioContextResponse = {
  success: boolean;
  error: string | null;
  creatorProfileExists: boolean;
  activeReferenceExists: boolean;
  activeReferenceAssetId: number | null;
  activeReferenceLastUsedAt: string | null;
};

async function readSuccessfulJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return readJsonResponse<T>(await fetch(`${environment.apiBaseUrl}${path}`, { signal }));
}

async function readJsonResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";

  if (!response.ok) {
    const body = await response.text();
    let message = `Content Studio request failed with HTTP ${response.status}`;
    if (contentType.includes("application/json") && body) {
      try {
        const errorResult = JSON.parse(body) as { error?: string };
        message = errorResult.error || message;
      } catch {
        // The HTTP status remains the safe error when a proxy returns malformed JSON.
      }
    }
    throw new Error(message);
  }
  if (!contentType.includes("application/json")) {
    throw new Error("Content Studio returned a non-JSON response");
  }
  try {
    return (await response.json()) as T;
  } catch {
    throw new Error("Content Studio returned invalid JSON");
  }
}

async function postCreativeTagAction(
  path: string,
  body: object,
  signal?: AbortSignal,
): Promise<string> {
  const result = await readJsonResponse<CreativeTagActionResponse>(await fetch(
    `${environment.apiBaseUrl}${path}`,
    {
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
      method: "POST",
      signal,
    },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Creative tag action failed");
  }
  return result.tags;
}

export async function getContentStudioContext(signal?: AbortSignal): Promise<ContentStudioContext> {
  const result = await readSuccessfulJson<ContentStudioContextResponse>(
    "/content-studio/context",
    signal,
  );
  if (!result.success || result.error) {
    throw new Error(result.error || "Content Studio context read failed");
  }

  if (!result.creatorProfileExists) {
    return { status: "profile_missing", creatorProfileExists: false, activeReference: null };
  }
  if (!result.activeReferenceExists || result.activeReferenceAssetId === null) {
    return { status: "reference_missing", creatorProfileExists: true, activeReference: null };
  }
  return {
    status: "ready",
    creatorProfileExists: true,
    activeReference: {
      assetId: result.activeReferenceAssetId,
      lastUsedAt: result.activeReferenceLastUsedAt,
    },
  };
}

export async function getContentStudioConfiguration(
  signal?: AbortSignal,
): Promise<ContentStudioConfiguration> {
  const result = await readSuccessfulJson<ContentStudioConfiguration>(
    "/content-studio/configuration",
    signal,
  );
  if (!result.success || result.error) {
    throw new Error(result.error || "Content Studio configuration read failed");
  }
  return result;
}

export function enhanceCreativeTags(
  tags: string,
  explicit: boolean,
  signal?: AbortSignal,
  context?: {
    origin: "canonical_planner" | "manual_creative_concept";
    plannerQuestion?: string;
    plannerItemId?: string;
    plannerItemTitle?: string;
  },
): Promise<string> {
  return postCreativeTagAction(
    "/content-studio/creative-tags/enhance",
    { explicit, tags, ...context },
    signal,
  );
}

export async function generatePromptWorkshopBatch(
  lane: PromptWorkshopLane,
  requestText: string,
  promptCount: number,
  signal?: AbortSignal,
): Promise<PromptWorkshopBatch> {
  const result = await readJsonResponse<PromptWorkshopBatchResponse>(await fetch(
    `${environment.apiBaseUrl}/content-studio/prompt-workshop/generate`,
    {
      body: JSON.stringify({ lane, promptCount, requestText }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
      signal,
    },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Prompt Workshop failed");
  }
  return result.batch;
}

export async function getPromptWorkshopArchive(
  signal?: AbortSignal,
): Promise<PromptWorkshopBatch[]> {
  const result = await readSuccessfulJson<PromptWorkshopArchiveResponse>(
    "/content-studio/prompt-workshop/archive",
    signal,
  );
  if (!result.success || result.error) {
    throw new Error(result.error || "Prompt Workshop archive failed");
  }
  return result.batches;
}

export async function markPromptWorkshopPromptUsed(
  batchId: string,
  promptNumber: number,
): Promise<void> {
  const result = await readJsonResponse<{ success: boolean; error: string | null }>(await fetch(
    `${environment.apiBaseUrl}/content-studio/prompt-workshop/archive/${encodeURIComponent(batchId)}/use`,
    {
      body: JSON.stringify({ promptNumber }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Prompt Workshop usage update failed");
  }
}

export async function createPromptPreview(
  creativeMode: string,
  creativeTags: string,
  promptCount: number,
  signal?: AbortSignal,
): Promise<PromptPreview> {
  const result = await readJsonResponse<PromptPreviewResponse>(await fetch(
    `${environment.apiBaseUrl}/content-studio/prompt-preview`,
    {
      body: JSON.stringify({ creativeMode, creativeTags, promptCount }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
      signal,
    },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Prompt Preview failed");
  }
  return result.preview;
}

export async function askPromptPlanner(question: string, image?: File | null): Promise<string> {
  const body = new FormData();
  body.append("question", question);
  if (image) body.append("image", image, image.name);
  const result = await readJsonResponse<PromptPlannerResponse>(await fetch(
    `${environment.apiBaseUrl}/content-studio/prompt-planner/ask`,
    { body, method: "POST" },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Canonical Prompt Planner request failed");
  }
  return result.answer;
}

export async function submitContentStudioGeneration(request: GenerationSubmission): Promise<string> {
  const result = await readJsonResponse<{ success: boolean; error: string | null; runId: string }>(await fetch(
    `${environment.apiBaseUrl}/content-studio/generations`,
    {
      body: JSON.stringify(request),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  ));
  if (!result.success || result.error) throw new Error(result.error || "Generation submission failed");
  return result.runId;
}

export async function submitAutonomousInspiration(
  provider: string,
): Promise<string> {
  const result = await readJsonResponse<{
    success: boolean;
    error: string | null;
    runId: string;
  }>(await fetch(
    `${environment.apiBaseUrl}/content-studio/inspire`,
    {
      body: JSON.stringify({ provider }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    },
  ));
  if (!result.success || result.error) {
    throw new Error(result.error || "Autonomous inspiration failed");
  }
  return result.runId;
}

export async function getContentStudioGeneration(runId: string): Promise<ContentStudioGeneration> {
  const result = await readSuccessfulJson<{
    success: boolean;
    error: string | null;
    generation: ContentStudioGeneration;
  }>(`/content-studio/generations/${encodeURIComponent(runId)}`);
  if (!result.success || result.error) throw new Error(result.error || "Generation status failed");
  return result.generation;
}
