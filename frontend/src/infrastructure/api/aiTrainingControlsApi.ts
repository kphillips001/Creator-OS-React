import { environment } from "../config/environment";
import { developerFetch } from "./developerFetch";

export type TrainingStatus = "DRAFT" | "ENABLED" | "DISABLED" | "ARCHIVED" | "REQUIRES_IMPLEMENTATION";
export type TrainingInstruction = {
  instructionId: string; instructionType: string; originalOperatorText: string;
  normalizedInstruction: string; status: TrainingStatus; priority: number;
  classificationReason: string | null; version: number; createdAt: string; updatedAt: string;
  policyKey: string | null; enforcementMode: string;
  enabledAt: string | null; disabledAt: string | null; archivedAt: string | null;
  runtimeRecognized?: boolean;
  implementationStatus?: { implemented:boolean; label:string };
  customerFanvueUserId?: number | null;
  policyConfiguration?: Record<string, number | boolean | string>;
  scope?: "GLOBAL" | "CUSTOMER";
  businessAuthorityChanged?: boolean; safetyConflict?: boolean;
};
export type TrainingPreview = {
  originalOperatorText: string; normalizedInstruction: string; instructionType: string;
  classification: string; classificationReason: string; runtimeEligible: boolean;
  policyKey: string | null; enforcementMode: string;
  policyConfiguration?: Record<string, number | boolean | string>;
  scope?: "GLOBAL" | "CUSTOMER";
  businessAuthorityChanged?: boolean; safetyConflict?: boolean;
};
export type TrainingRevision = { version: number; action: string; normalized_instruction: string; status: string; priority: number; enforcement_mode?: string; created_at: string };
export type CustomerTreatment = { sales_pressure: "REDUCED"|"NORMAL"|"INCREASED"; free_engagement: "MORE_LIMITED"|"NORMAL"|"MORE_FLEXIBLE"; response_length: "SHORTER"|"NORMAL"|"LONGER" };
export type CustomerTreatmentResult = { eligible?: boolean; eligibilityReason?: string|null; configuration: CustomerTreatment; usingAvaDefaults: boolean; runtimeEffect: "BOUNDED_PHASE_2B"; item: TrainingInstruction|null };
export type CustomerTrainingPlan = { operatorText:string; supported:boolean; classification:string; explanation:string; conversationGuidance:string[]; treatment:CustomerTreatment; protectedAuthorities:string[] };
export type ImplementationBrief={version:number;request:string;scope:string;whyImplementationIsRequired:string;desiredBehavior:string;protectedAuthorities:string[];acceptanceCriteria:string[];regressionBoundaries:string[];proposedVerification:string[];repository:string;branch:string};
export type ImplementationExecution={execution_id:string;task_id:string;status:string;started_at:string|null;completed_at:string|null;failure_reason:string|null;final_report:Record<string,unknown>|null;review_status:string|null};
export type ImplementationAttempt={attemptId:string;attemptNumber:number;briefVersion:number;taskId:string;executionId:string|null;status:string;approvedAt:string|null;startedAt:string|null;completedAt:string|null;verifiedAt:string|null;createdAt:string|null;updatedAt:string|null;isCurrent:boolean;execution:ImplementationExecution|null};
export type TrainingWorkItem = { workItemId:string; scope:"GLOBAL"|"CUSTOMER"; customerFanvueUserId:number|null; originalRequestText:string; status:string; classification:string|null; classificationRationale:string|null; analysis:Record<string,unknown>; linkedInstructionId:string|null; linkedFutureTaskId:string|null; createdAt:string; updatedAt:string; completedAt:string|null;implementation?:{brief:ImplementationBrief|null;execution:ImplementationExecution|null;currentAttempt?:ImplementationAttempt|null;attempts?:ImplementationAttempt[]} };

const base = `${environment.apiBaseUrl}/ai-training-controls`;
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { cache: "no-store", ...init });
  const value = await response.json().catch(() => null) as T & { detail?: string };
  if (!response.ok) throw new Error(value?.detail || "Unable to update AI Training.");
  return value;
}
async function developerRequest<T>(path:string,init?:RequestInit):Promise<T>{const response=await developerFetch(`${base}${path}`,{cache:"no-store",...init});const value=await response.json().catch(()=>null) as T&{detail?:string};if(!response.ok)throw new Error(value?.detail||"Unable to update implementation handoff.");return value;}
const json = (body: unknown): RequestInit => ({ headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const aiTrainingControlsApi = {
  list: () => request<{ items: TrainingInstruction[] }>(""),
  preview: (operatorText: string) => request<TrainingPreview>("/preview", { method: "POST", ...json({ operatorText }) }),
  create: (operatorText: string, priority: number, activate: boolean, policyConfiguration?: Record<string, number | boolean | string>) => request<TrainingInstruction>("", { method: "POST", ...json({ operatorText, priority, activate, policyConfiguration }) }),
  edit: (id: string, operatorText: string, priority: number, policyConfiguration?: Record<string, number | boolean | string>) => request<TrainingInstruction>(`/${encodeURIComponent(id)}`, { method: "PATCH", ...json({ operatorText, priority, policyConfiguration }) }),
  transition: (id: string, action: "enable" | "disable" | "archive") => request<TrainingInstruction>(`/${encodeURIComponent(id)}/${action}`, { method: "POST" }),
  history: (id: string) => request<{ items: TrainingRevision[] }>(`/${encodeURIComponent(id)}/history`),
  customerPreview: (operatorText: string) => request<TrainingPreview>("/customer-preview", { method: "POST", ...json({ operatorText }) }),
  customerAnalyze: (key:string,operatorText:string) => request<CustomerTrainingPlan>(`/customers/${encodeURIComponent(key)}/analyze`,{method:"POST",...json({operatorText})}),
  customerApplyPlan: (key:string,plan:CustomerTrainingPlan) => request<{guidance:TrainingInstruction[];treatment:TrainingInstruction|null;configuration:CustomerTreatment;usingAvaDefaults:boolean}>(`/customers/${encodeURIComponent(key)}/apply-plan`,{method:"POST",...json({operatorText:plan.operatorText,conversationGuidance:plan.conversationGuidance,treatment:{salesPressure:plan.treatment.sales_pressure,freeEngagement:plan.treatment.free_engagement,responseLength:plan.treatment.response_length}})}),
  allCustomerRules: () => request<{ items: TrainingInstruction[] }>("/customers"),
  accountCustomerHistory: (id: string) => request<{ items: TrainingRevision[] }>(`/customer-history/${encodeURIComponent(id)}`),
  customerList: (key: string) => request<{ eligible: boolean; eligibilityReason: string | null; items: TrainingInstruction[] }>(`/customers/${encodeURIComponent(key)}`),
  customerCreate: (key: string, operatorText: string, priority: number, activate: boolean) => request<TrainingInstruction>(`/customers/${encodeURIComponent(key)}`, { method: "POST", ...json({ operatorText, priority, activate }) }),
  customerEdit: (key: string, id: string, operatorText: string, priority: number) => request<TrainingInstruction>(`/customers/${encodeURIComponent(key)}/${encodeURIComponent(id)}`, { method: "PATCH", ...json({ operatorText, priority }) }),
  customerTransition: (key: string, id: string, action: "enable" | "disable" | "archive") => request<TrainingInstruction>(`/customers/${encodeURIComponent(key)}/${encodeURIComponent(id)}/${action}`, { method: "POST" }),
  customerHistory: (key: string, id: string) => request<{ items: TrainingRevision[] }>(`/customers/${encodeURIComponent(key)}/${encodeURIComponent(id)}/history`),
  treatmentGet: (key: string) => request<CustomerTreatmentResult>(`/customer-treatment/${encodeURIComponent(key)}`),
  treatmentPreview: (value: CustomerTreatment) => request<Omit<CustomerTreatmentResult,"item"> & { protectedAuthorities: string[]; treatmentType: string }>("/customer-treatment/preview", { method: "POST", ...json({ salesPressure:value.sales_pressure, freeEngagement:value.free_engagement, responseLength:value.response_length }) }),
  treatmentApply: (key: string, value: CustomerTreatment) => request<CustomerTreatmentResult>(`/customer-treatment/${encodeURIComponent(key)}`, { method: "PUT", ...json({ salesPressure:value.sales_pressure, freeEngagement:value.free_engagement, responseLength:value.response_length }) }),
  treatmentDisable: (key: string, id: string) => request<TrainingInstruction>(`/customer-treatment/${encodeURIComponent(key)}/${encodeURIComponent(id)}/disable`, { method: "POST" }),
  treatmentHistory: (key: string, id: string) => request<{ items: TrainingRevision[] }>(`/customer-treatment/${encodeURIComponent(key)}/${encodeURIComponent(id)}/history`),
  queueList:()=>request<{items:TrainingWorkItem[]}>("/queue"),
  queueAdd:(originalRequestText:string,scope:"GLOBAL"|"CUSTOMER",customerProjectionKey?:string)=>request<TrainingWorkItem>("/queue",{method:"POST",...json({originalRequestText,scope,customerProjectionKey})}),
  queueEdit:(id:string,originalRequestText:string)=>request<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}`,{method:"PATCH",...json({originalRequestText})}),
  queueAction:(id:string,action:"analyze"|"apply"|"close")=>request<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}/${action}`,{method:"POST"}),
  implementationPrepare:(id:string)=>developerRequest<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}/implementation/prepare`,{method:"POST"}),
  implementationStart:(id:string)=>developerRequest<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}/implementation/start`,{method:"POST"}),
  implementationDetail:(id:string)=>developerRequest<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}/implementation`),
  implementationVerify:(id:string)=>developerRequest<TrainingWorkItem>(`/queue/${encodeURIComponent(id)}/implementation/verify`,{method:"POST"}),
  historyView:()=>request<{baselineAt:string|null;items:TrainingInstruction[]}>("/history-view"),
};
