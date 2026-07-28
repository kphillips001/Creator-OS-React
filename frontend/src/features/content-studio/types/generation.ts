export type GenerationStatus = "queued" | "planning" | "running" | "succeeded" | "partial" | "failed";

export type ContentStudioGeneration = {
  runId: string;
  jobId: string | null;
  promptPlanId: string | null;
  status: GenerationStatus;
  message: string;
  provider: string;
  completedCount: number;
  failedCount: number;
  processedCount: number;
  totalCount: number;
  progress: number;
  images: { index: number; url: string }[];
};

export type GenerationSubmission = {
  provider: string;
  promptSource: string;
  promptSourceLabel: string;
  promptBatch: string[];
  creativeMode: string;
  promptCount: number;
  creatorContext: { status: string; activeReferenceAssetId: number | null };
  origin?: "canonical_planner";
  plannerLineage?: {
    plannerQuestion: string;
    plannerItemId: string;
    plannerItemTitle: string;
    selectedPlannerItem: string;
    enhancedResult: string;
  };
};
