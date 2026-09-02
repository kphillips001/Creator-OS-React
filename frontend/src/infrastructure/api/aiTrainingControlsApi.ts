import { environment } from "../config/environment";

export type TrainingStatus = "DRAFT" | "ENABLED" | "DISABLED" | "ARCHIVED" | "REQUIRES_IMPLEMENTATION";
export type TrainingInstruction = {
  instructionId: string; instructionType: string; originalOperatorText: string;
  normalizedInstruction: string; status: TrainingStatus; priority: number;
  classificationReason: string | null; version: number; createdAt: string; updatedAt: string;
  policyKey: string | null; enforcementMode: string;
  enabledAt: string | null; disabledAt: string | null; archivedAt: string | null;
  runtimeRecognized?: boolean;
  policyConfiguration?: Record<string, number | boolean | string>;
};
export type TrainingPreview = {
  originalOperatorText: string; normalizedInstruction: string; instructionType: string;
  classification: string; classificationReason: string; runtimeEligible: boolean;
  policyKey: string | null; enforcementMode: string;
  policyConfiguration?: Record<string, number | boolean | string>;
};

const base = `${environment.apiBaseUrl}/ai-training-controls`;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store", ...init });
  const value = await response.json().catch(() => null) as T & { detail?: string };
  if (!response.ok) throw new Error(value?.detail || "Unable to update AI Training.");
  return value;
}
const json = (body: unknown): RequestInit => ({ headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const aiTrainingControlsApi = {
  list: () => request<{ items: TrainingInstruction[] }>(""),
  preview: (operatorText: string) => request<TrainingPreview>("/preview", { method: "POST", ...json({ operatorText }) }),
  create: (operatorText: string, priority: number, activate: boolean, policyConfiguration?: Record<string, number | boolean | string>) => request<TrainingInstruction>("", { method: "POST", ...json({ operatorText, priority, activate, policyConfiguration }) }),
  edit: (id: string, operatorText: string, priority: number, policyConfiguration?: Record<string, number | boolean | string>) => request<TrainingInstruction>(`/${encodeURIComponent(id)}`, { method: "PATCH", ...json({ operatorText, priority, policyConfiguration }) }),
  transition: (id: string, action: "enable" | "disable" | "archive") => request<TrainingInstruction>(`/${encodeURIComponent(id)}/${action}`, { method: "POST" }),
};
