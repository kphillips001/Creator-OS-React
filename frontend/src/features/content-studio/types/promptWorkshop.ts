export type PromptWorkshopLane = "premium" | "explicit";

export type PromptWorkshopBatch = {
  batchId: string;
  requestText: string;
  lane: PromptWorkshopLane;
  prompts: string[];
  usedPromptNumbers: number[];
  createdAt: string;
};

export type PromptWorkshopBatchResponse = {
  success: boolean;
  error: string | null;
  batch: PromptWorkshopBatch;
};

export type PromptWorkshopArchiveResponse = {
  success: boolean;
  error: string | null;
  batches: PromptWorkshopBatch[];
};
