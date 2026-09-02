export type PlannerBatchItemStatus = "pending" | "enhancing" | "submitting" | "generating" | "completed" | "failed";

export type PlannerBatchItem = {
  id: string;
  ordinal: number;
  status: PlannerBatchItemStatus;
  imageUrl: string;
  jobId: string | null;
  error: string;
  failureStage?: "enhancement" | "planning" | "generation";
  attempts?: Array<{
    attemptNumber: number;
    operationId: string | null;
    generationJobId?: string | null;
    status: "completed" | "failed";
    error?: string | null;
    failureStage?: "enhancement" | "planning" | "generation" | null;
  }>;
  retryCycleId?: string;
};

export function updatePlannerBatchItems(
  items: PlannerBatchItem[],
  id: string,
  changes: Partial<PlannerBatchItem>,
) {
  return items.map((item) => (item.id === id ? { ...item, ...changes } : item));
}
