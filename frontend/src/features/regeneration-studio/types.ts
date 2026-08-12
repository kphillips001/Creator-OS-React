export type RegenerationSource = {
  generatedImageId: string;
  mediaUrl: string;
  providerDisplayName: string;
  modelDisplayName: string | null;
  sourceWorkflow: string | null;
  creativeMode: string | null;
};

export type RegenerationResult = {
  resultId: string;
  variationIndex: number;
  status: string;
  generatedImageId: string | null;
  generationRecipeId: string | null;
  disposition: "PENDING_REVIEW" | "PROMOTED" | string;
  mediaUrl: string | null;
  errorCode: string | null;
  errorMessage: string | null;
};

export type RegenerationWorkspace = {
  success: boolean;
  operation: { status: string; progressCurrent: number; progressTotal: number; progressPercent: number; currentStage: string | null; stageMessage: string | null; errorMessage: string | null; metadata: Record<string, unknown> };
  run: { operationId: string; sourceGeneratedImageId: string; requestedCount: number; status: string };
  results: RegenerationResult[];
  error?: string;
};
