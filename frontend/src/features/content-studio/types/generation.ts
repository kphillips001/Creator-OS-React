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

export type ExplicitGenerationInput = {
  sourceText: string;
  originalSource: string;
  sourceType: "operator_tags_or_prose" | "selected_inspiration_concept";
  origin: "explicit_tags" | "explicit_inspiration";
  conceptTier?: "hardcore" | "softcore";
  requiredSemanticAttributes: Record<string, string[]>;
  requestedImageCount: number;
  collectionId?: string;
  lineage: Record<string, unknown>;
};

export type GenerationSubmission = {
  provider: string;
  promptSource: string;
  promptSourceLabel: string;
  promptBatch: string[];
  creativeMode: string;
  promptCount: number;
  creatorContext: { status: string; activeReferenceAssetId: number | null };
  origin?: "canonical_planner" | "explicit_tags" | "explicit_inspiration";
  plannerLineage?: {
    plannerQuestion: string;
    plannerItemId: string;
    plannerItemTitle: string;
    selectedPlannerItem: string;
    enhancedResult: string;
  };
  lane?: "social" | "explicit";
  explicitInput?: ExplicitGenerationInput;
};
